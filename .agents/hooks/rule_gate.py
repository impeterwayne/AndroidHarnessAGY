#!/usr/bin/env python3
"""PreToolUse gate: enforce this workspace's Kotlin rules on agent file writes.

Turns assertions that currently live only in prompts (AGENTS.md, rules/ponytail.md)
into deterministic checks:

  kotlin-comment    no `//` or block comments in Kotlin sources (KDoc `/** */` is allowed)
  hardcoded-string  no literal strings in user-facing Compose params -- use stringResource()
  raw-hex-color     no Color(0x…) / "#RRGGBB" outside :core:designsystem -- use AppTheme tokens

Why PreToolUse and not PostToolUse: the PostToolUse payload carries no `toolCall`,
so it cannot know which file was written. PreToolUse carries `toolCall.args`, and
can `deny` with a reason the model can act on *before* the bad write lands.

Fail-open by design. Any internal error, unknown argument shape, or non-Kotlin
target yields PASS_DECISION -- a buggy gate that blocks work is worse than one that
misses a violation.

Usage:
  hooks/rule_gate.py                 # hook mode: JSON payload on stdin, directive on stdout
  hooks/rule_gate.py --self-test     # fixture assertions, exits nonzero on failure
  hooks/rule_gate.py --scan PATH...  # false-positive sweep over existing sources
"""

import json
import re
import sys
from pathlib import Path

# Pass-through verdict for writes with no violation.
#   "ask"   -- preserves the normal confirmation flow, and respects cached
#              "Always Allow" decisions. Conservative default: the gate changes
#              *nothing* about approvals, it only blocks violations.
#   "allow" -- clean Kotlin writes stop prompting. Faster, but it is a real change
#              to the approval UX; opt in deliberately.
PASS_DECISION = "ask"

STATE_DIR = Path(__file__).resolve().parent.parent / "state"
UNKNOWN_ARGS_LOG = STATE_DIR / "rule_gate_unknown_args.jsonl"

MAX_REPORTED = 10

# Compose parameters whose value is rendered to the user.
# `label` is deliberately absent: in Compose it is overwhelmingly an animation
# tooling label (animateFloatAsState, rememberInfiniteTransition, animateFloat),
# not user-facing text. Including it produced only false positives on this codebase.
UI_TEXT_PARAMS = (
    "text", "contentDescription", "placeholder", "title", "subtitle",
    "hint", "supportingText", "errorMessage", "message",
)

# Anchored at end-of-code-before-the-literal: the param assignment must sit
# immediately in front of the string that is being opened.
RE_UI_PARAM_LITERAL = re.compile(
    r"\b(" + "|".join(UI_TEXT_PARAMS) + r")\s*=\s*$", re.IGNORECASE
)
# `val text = "…"` is a local binding, not a rendered parameter.
RE_LOCAL_BINDING = re.compile(r"\b(?:val|var)\s+\w+\s*=\s*$")
RE_COLOR_HEX = re.compile(r"\bColor\s*\(\s*0[xX][0-9a-fA-F]{6,8}")
RE_HEX_STRING = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
RE_PREVIEW_ANNOTATION = re.compile(r"@\w*Preview\w*\b")
RE_FUN_DECL = re.compile(r"\bfun\s+\w+")


class Scan:
    """Single pass over Kotlin source, separating code from strings and comments."""

    def __init__(self, text):
        self.comments = []       # (line, token) for // and /* */, excluding KDoc
        self.strings = []        # (line, value, code_before_on_that_line)
        self.code_lines = {}     # line -> code with string bodies blanked out
        self._scan(text)

    def _scan(self, text):
        i, n = 0, len(text)
        line = 1
        code_buf = {}

        def emit(ln, s):
            code_buf.setdefault(ln, []).append(s)

        while i < n:
            ch = text[i]
            nxt = text[i + 1] if i + 1 < n else ""

            if ch == "\n":
                line += 1
                i += 1
                continue

            # line comment
            if ch == "/" and nxt == "/":
                end = text.find("\n", i)
                end = n if end == -1 else end
                self.comments.append((line, "//"))
                i = end
                continue

            # block comment -- KDoc (/**) is permitted documentation, /* is not
            if ch == "/" and nxt == "*":
                is_kdoc = text[i:i + 3] == "/**"
                end = text.find("*/", i + 2)
                end = n if end == -1 else end + 2
                if not is_kdoc:
                    self.comments.append((line, "/* */"))
                line += text.count("\n", i, end)
                i = end
                continue

            # raw string
            if text[i:i + 3] == '"""':
                end = text.find('"""', i + 3)
                end = n if end == -1 else end + 3
                self.strings.append((line, text[i + 3:max(end - 3, i + 3)], "".join(code_buf.get(line, []))))
                line += text.count("\n", i, end)
                i = end
                continue

            # regular string
            if ch == '"':
                j = i + 1
                buf = []
                while j < n and text[j] != '"':
                    if text[j] == "\\" and j + 1 < n:
                        buf.append(text[j + 1])
                        j += 2
                        continue
                    if text[j] == "\n":
                        break
                    buf.append(text[j])
                    j += 1
                self.strings.append((line, "".join(buf), "".join(code_buf.get(line, []))))
                emit(line, '""')
                i = j + 1
                continue

            emit(line, ch)
            i += 1

        self.code_lines = {ln: "".join(parts) for ln, parts in code_buf.items()}


def preview_lines(text):
    """Line numbers inside a @Preview-annotated function, plus @Preview arg lines.

    Preview composables legitimately hold literal sample text, and
    @Preview(backgroundColor = 0xFF000000) must be a Long constant -- a token
    cannot be used there.
    """
    lines = text.splitlines()
    skip = set()
    i = 0
    while i < len(lines):
        if RE_PREVIEW_ANNOTATION.search(lines[i]):
            # the annotation itself, across any wrapped argument list
            depth = 0
            j = i
            while j < len(lines):
                skip.add(j + 1)
                depth += lines[j].count("(") - lines[j].count(")")
                if j > i or depth <= 0:
                    if depth <= 0:
                        break
                j += 1
            # then the function body it annotates
            k = j
            while k < len(lines) and not RE_FUN_DECL.search(lines[k]):
                skip.add(k + 1)
                k += 1
            depth = 0
            started = False
            while k < len(lines):
                skip.add(k + 1)
                depth += lines[k].count("{") - lines[k].count("}")
                if "{" in lines[k]:
                    started = True
                if started and depth <= 0:
                    break
                k += 1
            i = k + 1
            continue
        i += 1
    return skip


def check(path, text):
    """Return a list of (rule, line, detail)."""
    p = path.replace("\\", "/")
    if not p.endswith(".kt"):
        return []
    if "/src/test/" in p or "/src/androidTest/" in p or "/build/" in p:
        return []

    in_designsystem = "designsystem" in p.lower()
    skip = preview_lines(text)
    scan = Scan(text)
    out = []

    for line, token in scan.comments:
        if line in skip:
            continue
        out.append(("kotlin-comment", line, f"`{token}` comment"))

    for line, value, code_before in scan.strings:
        if line in skip:
            continue
        if not value.strip():
            continue
        m = RE_UI_PARAM_LITERAL.search(code_before)
        if m and not RE_LOCAL_BINDING.search(code_before):
            param = m.group(1)
            out.append((
                "hardcoded-string", line,
                f'{param} = "{value[:40]}" -- declare in strings.xml and use stringResource()',
            ))
        if not in_designsystem and RE_HEX_STRING.match(value.strip()):
            out.append(("raw-hex-color", line, f'"{value}" -- use AppTheme.colorScheme tokens'))

    if not in_designsystem:
        for line, code in scan.code_lines.items():
            if line in skip:
                continue
            m = RE_COLOR_HEX.search(code)
            if m:
                out.append(("raw-hex-color", line, f"{m.group(0)}…) -- use AppTheme.colorScheme tokens"))

    return sorted(out, key=lambda v: (v[1], v[0]))


def extract_target(args):
    """Best-effort (path, content) from tool args. Returns (None, None) if unsure."""
    if not isinstance(args, dict):
        return None, None
    path = content = None
    for key, val in args.items():
        if not isinstance(val, str):
            continue
        k = key.lower()
        if path is None and ("targetfile" in k or k.endswith("path") or k == "file"):
            path = val
        elif "content" in k or "code" in k or "replacement" in k or "text" in k:
            content = val if content is None else content + "\n" + val
    return path, content


def log_unknown(payload):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with UNKNOWN_ARGS_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload)[:4000] + "\n")
    except Exception:
        pass


def hook_mode():
    verdict = {"decision": PASS_DECISION}
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        call = payload.get("toolCall") or {}
        path, content = extract_target(call.get("args"))

        if not path or content is None:
            # Argument shape for this tool is not understood yet -- record it so one
            # real run reveals the schema, and never block on a guess.
            log_unknown({"tool": call.get("name"), "argKeys": sorted((call.get("args") or {}).keys())})
        else:
            violations = check(path, content)
            if violations:
                shown = violations[:MAX_REPORTED]
                lines = [f"  line {ln}: [{rule}] {detail}" for rule, ln, detail in shown]
                extra = len(violations) - len(shown)
                if extra > 0:
                    lines.append(f"  … and {extra} more")
                verdict = {
                    "decision": "deny",
                    "reason": (
                        f"Workspace rule violation in {Path(path).name} "
                        f"({len(violations)} issue(s)). Fix and retry:\n"
                        + "\n".join(lines)
                        + "\nSee AGENTS.md and .agents/rules/ponytail.md."
                    ),
                }
    except Exception as exc:
        print(f"rule_gate: {type(exc).__name__}: {exc}", file=sys.stderr)

    print(json.dumps(verdict))


FIXTURES = [
    # (name, path, source, expected rule ids)
    ("clean composable", "feature/home/HomeScreen.kt", '''
@Composable
fun HomeScreen(state: UiState, onEvent: (Event) -> Unit) {
    Column(modifier = Modifier.padding(AppTheme.spacing.medium)) {
        AppText(text = stringResource(R.string.home_title), color = AppTheme.colorScheme.onSurface)
    }
}
''', set()),
    ("line comment", "feature/home/HomeScreen.kt", '''
@Composable
fun HomeScreen() {
    // set up the column
    Column {}
}
''', {"kotlin-comment"}),
    ("kdoc allowed", "core/domain/GetUserUseCase.kt", '''
/**
 * Returns the signed-in user.
 */
class GetUserUseCase
''', set()),
    ("url is not a comment", "core/network/Api.kt", '''
const val BASE = "https://api.example.com/v1"
''', set()),
    ("hardcoded ui string", "feature/home/HomeScreen.kt", '''
@Composable
fun HomeScreen() {
    AppText(text = "Screen Mirroring")
}
''', {"hardcoded-string"}),
    ("raw hex color", "feature/home/HomeScreen.kt", '''
@Composable
fun HomeScreen() {
    Box(modifier = Modifier.background(Color(0xFF000517)))
}
''', {"raw-hex-color"}),
    ("hex string literal", "feature/home/Theme.kt", '''
val bg = "#000517"
''', {"raw-hex-color"}),
    ("designsystem may define colors", "core/designsystem/theme/Color.kt", '''
val Navy = Color(0xFF000517)
val NavyHex = "#000517"
''', set()),
    ("preview may hold literals and hex", "feature/home/HomeScreen.kt", '''
@Preview(backgroundColor = 0xFF000517, showBackground = true)
@Composable
private fun HomeScreenPreview() {
    AppText(text = "Sample title")
}
''', set()),
    ("tests exempt", "feature/home/src/test/HomeScreenTest.kt", '''
// arrange
val label = "whatever"
''', set()),
    ("string containing slashes", "core/common/Paths.kt", '''
val sep = "//"
''', set()),
    ("local val named text is not a ui param", "core/common/Fmt.kt", '''
val text = "internal marker"
''', set()),
    ("block comment", "core/common/Paths.kt", '''
/* legacy */
val x = 1
''', {"kotlin-comment"}),
]


def self_test():
    failures = 0
    for name, path, src, expected in FIXTURES:
        got = {rule for rule, _, _ in check(path, src)}
        ok = got == expected
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(f"        expected {sorted(expected) or '[]'}, got {sorted(got) or '[]'}")
            for rule, ln, detail in check(path, src):
                print(f"        line {ln}: [{rule}] {detail}")
    print(f"\n{len(FIXTURES) - failures}/{len(FIXTURES)} fixtures passed")
    return 1 if failures else 0


def scan_mode(roots):
    from collections import Counter
    counts = Counter()
    per_file = []
    total = 0
    for root in roots:
        for f in sorted(Path(root).rglob("*.kt")):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            total += 1
            v = check(str(f), text)
            if v:
                per_file.append((str(f), v))
                for rule, _, _ in v:
                    counts[rule] += 1
    print(f"scanned {total} Kotlin files")
    print(f"violations by rule: {dict(counts) or 'none'}")
    print(f"files with violations: {len(per_file)}/{total}\n")
    for path, v in per_file:
        print(f"{path}  ({len(v)})")
        for rule, ln, detail in v[:6]:
            print(f"    line {ln}: [{rule}] {detail}")
        if len(v) > 6:
            print(f"    … and {len(v) - 6} more")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    if "--scan" in sys.argv:
        sys.exit(scan_mode(sys.argv[sys.argv.index("--scan") + 1:]))
    hook_mode()
