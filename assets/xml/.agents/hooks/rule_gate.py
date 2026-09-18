#!/usr/bin/env python3
"""PreToolUse gate: enforce this workspace's Kotlin rules on agent file writes.

Turns assertions that currently live only in prompts (rules/android.md, rules/lean.md)
into deterministic checks:

  kotlin-comment    no `//` or block comments in Kotlin sources (KDoc `/** */` is allowed)
  hardcoded-string  no literal strings in user-facing Compose params -- use stringResource()
  raw-hex-color     no Color(0x…) / "#RRGGBB" outside :core:designsystem -- use AppTheme tokens

and, on XML resources:

  xml-hardcoded-string  no literal android:text / hint / contentDescription -- use @string/…
  xml-raw-hex-color     no "#RRGGBB" in a layout -- use @color/…
  xml-shape-drawable    no new <shape>/<selector>/<ripple> in res/drawable -- use ShapeView
                        `app:shape_*` attributes. Only active when `.agents/rules/xml.md`
                        is installed, since it is that rule which forbids them.

Why PreToolUse and not PostToolUse: the PostToolUse payload carries no `toolCall`,
so it cannot know which file was written. PreToolUse carries `toolCall.args`, and
can `deny` with a reason the model can act on *before* the bad write lands.

Fail-open by design. Any internal error, unknown argument shape, or non-Kotlin
target yields PASS_DECISION -- a buggy gate that blocks work is worse than one that
misses a violation.

Usage:
  hooks/rule_gate.py                 # hook mode: JSON payload on stdin, directive on stdout
  hooks/rule_gate.py --self-test     # fixture assertions, exits nonzero on failure
  hooks/rule_gate.py --scan PATH...  # false-positive sweep over existing sources (.kt and .xml)
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

# --- XML resources -------------------------------------------------------

# Attributes whose value is rendered to the user. `tools:` is design-time and exempt.
XML_TEXT_ATTRS = ("text", "hint", "contentDescription", "title", "summary")
RE_XML_TEXT_ATTR = re.compile(
    r'\b(?:android|app):(' + "|".join(XML_TEXT_ATTRS) + r')\s*=\s*"([^"]*)"'
)
RE_XML_HEX_ATTR = re.compile(r'\b(\w+):(\w+)\s*=\s*"(#[0-9a-fA-F]{3,8})"')
RE_XML_HAS_LETTER = re.compile(r"[^\W\d_]")
# The first real element of the document, past the prolog and any comments.
RE_XML_ROOT_TAG = re.compile(r"<([a-zA-Z][\w.\-]*)")
RE_XML_COMMENT = re.compile(r"<!--.*?-->", re.S)
RE_XML_PROLOG = re.compile(r"<\?.*?\?>", re.S)
# Drawable roots that ShapeView replaces. `vector`, `layer-list`, `animated-*` and the
# rest are genuine drawings, and stay in res/drawable.
SHAPE_DRAWABLE_ROOTS = ("shape", "selector", "ripple")

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"


def xml_track():
    """True when this project installed the View/XML rule rather than the Compose one."""
    try:
        return (RULES_DIR / "xml.md").is_file()
    except Exception:
        return False


def check_xml(p, text):
    """Return a list of (rule, line, detail) for an Android resource file."""
    out = []
    in_layout = "/res/layout" in p
    in_drawable = "/res/drawable" in p

    # Only the XML track forbids these -- a Compose project may legitimately keep them.
    if in_drawable and xml_track():
        stripped = RE_XML_COMMENT.sub("", RE_XML_PROLOG.sub("", text))
        m = RE_XML_ROOT_TAG.search(stripped)
        if m and m.group(1) in SHAPE_DRAWABLE_ROOTS:
            root = m.group(1)
            line = text[:text.find("<" + root)].count("\n") + 1
            out.append((
                "xml-shape-drawable", max(line, 1),
                f"<{root}> drawable -- express it with ShapeView `app:shape_*` attributes "
                f"on a com.genesys.shape view instead (skill: shape-view)",
            ))

    if not in_layout:
        return sorted(out, key=lambda v: (v[1], v[0]))

    for n, line in enumerate(text.splitlines(), start=1):
        for m in RE_XML_TEXT_ATTR.finditer(line):
            attr, value = m.group(1), m.group(2).strip()
            # `@string/...`, `?attr/...` and binding expressions are already resources.
            if not value or value[0] in "@?$":
                continue
            # Skip punctuation- and digit-only values: a bare "1" or "%" is not a
            # translatable phrase, and flagging it is pure noise.
            if not RE_XML_HAS_LETTER.search(value):
                continue
            out.append((
                "xml-hardcoded-string", n,
                f'{attr}="{value[:40]}" -- declare in strings.xml and use @string/...',
            ))
        for m in RE_XML_HEX_ATTR.finditer(line):
            ns, attr, value = m.group(1), m.group(2), m.group(3)
            if ns == "tools":
                continue
            out.append((
                "xml-raw-hex-color", n,
                f'{ns}:{attr}="{value}" -- declare in colors.xml and use @color/...',
            ))

    return sorted(out, key=lambda v: (v[1], v[0]))



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
    if "/src/test/" in p or "/src/androidTest/" in p or "/build/" in p:
        return []
    if p.endswith(".xml"):
        return check_xml(p, text)
    if not p.endswith(".kt"):
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
                        + "\nSee .agents/rules/"
                        + ("xml.md" if xml_track() else "android.md")
                        + " and .agents/rules/lean.md."
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
    ("clean layout", "feature/home/src/main/res/layout/fragment_home.xml", '''
<com.genesys.shape.layout.ShapeConstraintLayout
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    app:shape_radius="@dimen/radius_16"
    app:shape_solidColor="@color/surface_card">
    <TextView
        android:id="@+id/tvTitle"
        android:text="@string/home_title"
        android:textAppearance="@style/TextAppearance.App.TitleMedium" />
</com.genesys.shape.layout.ShapeConstraintLayout>
''', set()),
    ("hardcoded layout string", "feature/home/src/main/res/layout/fragment_home.xml", '''
<TextView android:text="Continue" />
''', {"xml-hardcoded-string"}),
    ("hardcoded content description", "feature/home/src/main/res/layout/item_doc.xml", '''
<ImageView android:contentDescription="Document thumbnail" />
''', {"xml-hardcoded-string"}),
    ("null content description is fine", "feature/home/src/main/res/layout/item_doc.xml", '''
<ImageView android:contentDescription="@null" />
''', set()),
    ("tools text is design-time", "feature/home/src/main/res/layout/item_doc.xml", '''
<TextView android:text="@string/x" tools:text="Sample title" />
''', set()),
    ("digit-only text is not a phrase", "feature/home/src/main/res/layout/item_doc.xml", '''
<TextView android:text="1" />
''', set()),
    ("raw hex in a layout", "feature/home/src/main/res/layout/fragment_home.xml", '''
<View app:shape_solidColor="#1E2025" />
''', {"xml-raw-hex-color"}),
    ("tools hex is design-time", "feature/home/src/main/res/layout/fragment_home.xml", '''
<View tools:background="#1E2025" />
''', set()),
    ("shape drawable is a shape-view job", "core/ui/src/main/res/drawable/bg_card.xml", '''
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/surface_card" />
    <corners android:radius="16dp" />
</shape>
''', {"xml-shape-drawable"}),
    ("selector drawable too", "core/ui/src/main/res/drawable/bg_chip.xml", '''
<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android" />
''', {"xml-shape-drawable"}),
    ("vector drawable is a real drawing", "core/ui/src/main/res/drawable/ic_close.xml", '''
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp" />
''', set()),
    ("values files are not layouts", "core/ui/src/main/res/values/colors.xml", '''
<resources>
    <color name="surface_card">#1E2025</color>
</resources>
''', set()),
]


def self_test():
    # The drawable rule only fires on the XML track; force it on so the fixture
    # asserts the logic rather than which profile happens to be installed here.
    globals()["xml_track"] = lambda: True
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
        sources = sorted(Path(root).rglob("*.kt")) + sorted(Path(root).rglob("*.xml"))
        for f in sources:
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
    print(f"scanned {total} source files")
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
