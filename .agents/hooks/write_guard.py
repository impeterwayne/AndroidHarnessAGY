#!/usr/bin/env python3
"""PreToolUse gate: the root session delegates code changes, it does not make them.

Re-homes the one invariant `mainAgent` cannot carry. `agy --agent <name>` does not load
a custom agent in CLI 1.1.22, so `orchestrator.md`'s empty write-tool list enforces
nothing. But the *shape* of the invariant does not need agent identity: it needs to know
whether the caller is the session the human is talking to, or a delegate.

The payload has no parent pointer. The signal is in the transcripts, and it has to be
read *directionally* — a plain "does another transcript mention my id" test matches both
ways round, because the relationship is recorded from both ends:

    parent, on spawning:   GENERIC  'Created the following subagents:\n{ "conversationId": "<child>"'
    child, on reporting:   GENERIC  'Message sent to "<parent>"'  + a send_message tool call

Both observed on 2026-08-27. So the test is the *spawn* record specifically:

    another transcript spawned me  ->  I am a delegate  ->  allow
    nothing spawned me            ->  I am the root     ->  deny source writes

The spawn record is written when the subagent is created, before the child runs, so this
signal is available from the child's first tool call.

Notes on the choices, because two of them look wrong at a glance:

- Only *source* files are gated. The invariant is "the orchestrator never writes code",
  not "never writes"; blocking notes, docs and plans would make the root session useless
  at the job it is supposed to do.
- Being a delegate is the *provable* side. Root is inferred from absence, which is also
  what a not-yet-flushed parent transcript looks like. That race is why this ships
  off by default, with an escape hatch that does not require editing code.

    python hooks/write_guard.py            # hook mode, reads a PreToolUse payload
    python hooks/write_guard.py --self-test
    python hooks/write_guard.py --status
    python hooks/write_guard.py --off / --on
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PASS_DECISION = "ask"  # never "allow": that would silently auto-approve every write

HOOKS_DIR = Path(__file__).resolve().parent
STATE_DIR = HOOKS_DIR.parent / "state" / "write_guard"
OFF_SWITCH = STATE_DIR / "off"

BRAIN_DIR = Path.home() / ".gemini" / "antigravity-cli" / "brain"
TRANSCRIPTS = (
    Path(".system_generated") / "logs" / "transcript_full.jsonl",
    Path(".system_generated") / "logs" / "transcript.jsonl",
)

# The parent writes this when it creates a subagent, alongside the child's
# conversationId. Observed 2026-08-27; it is the only directional marker available.
SPAWN_MARKER = b"Created the following subagents"

# Bound the sibling scan. Anything older than this cannot be our live parent.
SCAN_MAX_AGE_S = 24 * 60 * 60
SCAN_MAX_DIRS = 60
READ_CAP_BYTES = 4 * 1024 * 1024

SOURCE_SUFFIXES = {
    ".kt", ".kts", ".java", ".xml", ".pro", ".gradle",
    ".py", ".sh", ".ps1", ".json", ".toml", ".properties",
}
# Written by agents constantly and harmless; keep them out of the gate.
# `goals.json` is the ultrawork/loop contract -- gating it blocks step 2 of the very
# skill this rule exists to serve.
EXEMPT_NAMES = {"package.json", "tsconfig.json", "goals.json"}

# The invariant is about the *project's* code. An agent's own scratch space lives under
# ~/.gemini/antigravity-cli/brain/<conversationId>/scratch/ and is not project source, but
# it is full of .json and .py -- so a suffix test alone denies the agent its notepad.
PROJECT_ROOT = HOOKS_DIR.parent.parent


def in_project(path: str) -> bool:
    """True if path resolves inside the project that owns this hook. Errs toward True."""
    try:
        Path(path).resolve().relative_to(PROJECT_ROOT.resolve())
        return True
    except ValueError:
        return False
    except Exception:
        return True


def extract_target(args):
    """Best-effort target path from tool args. Mirrors rule_gate.extract_target."""
    if not isinstance(args, dict):
        return None
    for key, val in args.items():
        if not isinstance(val, str):
            continue
        k = key.lower()
        if "targetfile" in k or k.endswith("path") or k == "file":
            return val
    return None


def is_source(path: str) -> bool:
    p = Path(path)
    if p.name in EXEMPT_NAMES:
        return False
    if p.suffix.lower() in SOURCE_SUFFIXES:
        return True
    return p.name.endswith(".gradle.kts")


def transcript_for(brain: Path):
    for rel in TRANSCRIPTS:
        candidate = brain / rel
        if candidate.exists():
            return candidate
    return None


def spawned_by_another(conversation_id: str, brain_root: Path | None = None) -> bool:
    """True if some other conversation's transcript records *spawning* this one.

    Both the id and the spawn marker must appear in the same record, so a child's
    'Message sent to "<parent>"' report cannot make its parent look like a delegate.
    """
    root = brain_root or BRAIN_DIR
    if not conversation_id or not root.is_dir():
        return False

    needle = conversation_id.encode("utf-8", "ignore")
    now = time.time()

    candidates = []
    for entry in root.iterdir():
        if not entry.is_dir() or entry.name == conversation_id:
            continue
        try:
            age = now - entry.stat().st_mtime
        except OSError:
            continue
        if age > SCAN_MAX_AGE_S:
            continue
        candidates.append((age, entry))

    # Newest first: our parent is almost always the most recently touched sibling.
    candidates.sort(key=lambda pair: pair[0])

    for _, entry in candidates[:SCAN_MAX_DIRS]:
        path = transcript_for(entry)
        if path is None:
            continue
        try:
            with path.open("rb") as handle:
                read = 0
                for line in handle:
                    read += len(line)
                    if read > READ_CAP_BYTES:
                        break
                    if needle in line and SPAWN_MARKER in line:
                        return True
        except OSError:
            continue
    return False


def cache_path(conversation_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in conversation_id)
    return STATE_DIR / f"{safe}.json"


def read_cache(conversation_id: str):
    try:
        return json.loads(cache_path(conversation_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_cache(conversation_id: str, role: str) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path(conversation_id).write_text(
            json.dumps({"conversationId": conversation_id, "role": role, "ts": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        pass


def classify(conversation_id: str, brain_root: Path | None = None,
             state_dir: Path | None = None) -> str:
    """'delegate' | 'root' | 'unknown'. Cached: a conversation never changes role.

    Only 'delegate' is cached. 'root' is the inferred verdict, and inferring it early —
    before a parent has flushed its transcript — would otherwise stick for the session.
    """
    global STATE_DIR
    if state_dir is not None:
        STATE_DIR = state_dir

    if not conversation_id:
        return "unknown"

    cached = read_cache(conversation_id)
    if cached and cached.get("role") == "delegate":
        return "delegate"

    if spawned_by_another(conversation_id, brain_root):
        write_cache(conversation_id, "delegate")
        return "delegate"
    return "root"


def hook_mode() -> None:
    verdict = {"decision": PASS_DECISION}
    try:
        if OFF_SWITCH.exists():
            print(json.dumps(verdict))
            return

        payload = json.loads(sys.stdin.read() or "{}")
        call = payload.get("toolCall") or {}
        conversation_id = payload.get("conversationId") or ""
        path = extract_target(call.get("args"))

        if path and in_project(path) and is_source(path) and classify(conversation_id) == "root":
            verdict = {
                "decision": "deny",
                "reason": (
                    f"This session delegates code changes; it does not make them. "
                    f"{Path(path).name} must be written by a subagent.\n"
                    "  invoke_subagent(TypeName='executor')  every code change, one line "
                    "or one feature\n"
                    "Give it the goal, the constraints, and the file paths; then verify "
                    "its result with view_file.\n"
                    "To lift this for the session: run "
                    "`python .agents/hooks/write_guard.py --off`."
                ),
            }
    except Exception as exc:  # fail open: never block work over our own bug
        print(f"write_guard: {type(exc).__name__}: {exc}", file=sys.stderr)

    print(json.dumps(verdict))


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def self_test() -> int:
    import shutil
    import tempfile

    global STATE_DIR, OFF_SWITCH, BRAIN_DIR
    tmp = Path(tempfile.mkdtemp(prefix="write-guard-selftest-"))
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok   {name}")
        else:
            failures.append(f"{name}: {detail}")
            print(f"  FAIL {name} {detail}")

    def make_brain(root: Path, conv: str, body: str = "") -> Path:
        d = root / conv / ".system_generated" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "transcript_full.jsonl").write_text(body, encoding="utf-8")
        return root / conv

    def run_hook(payload: dict) -> dict:
        import io

        stdin, stdout = sys.stdin, sys.stdout
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.stdout = io.StringIO()
        try:
            hook_mode()
            return json.loads(sys.stdout.getvalue())
        finally:
            sys.stdin, sys.stdout = stdin, stdout

    try:
        brain = tmp / "brain"
        brain.mkdir()
        STATE_DIR = tmp / "state"
        OFF_SWITCH = STATE_DIR / "off"
        # hook_mode() calls classify() with no brain_root, so it reads the module global
        # rather than the fixture above. Without this line the deny fixtures scan the real
        # brain dir -- where any session that once viewed THIS FILE has a transcript record
        # containing both `conv-parent` and the spawn marker, which classifies the fixture
        # parent as a delegate and silently flips three deny checks to pass. Verified
        # 2026-08-28: conversation fd47254b did exactly that.
        BRAIN_DIR = brain

        # Record shapes copied from real transcripts, 2026-08-27. The exact strings
        # matter: an earlier version used a plain substring test and misread every
        # parent as a delegate, because the child names the parent when reporting back.
        def spawn_record(child_id: str) -> str:
            return json.dumps({
                "type": "GENERIC", "source": "MODEL",
                "content": 'Created the following subagents:\n{\n  "conversationId":  '
                           f'"{child_id}",\n  "typeName": "oracle"\n}}',
            }) + "\n"

        def report_record(parent_id: str) -> str:
            return json.dumps({
                "type": "GENERIC", "source": "MODEL",
                "content": f'Message sent to "{parent_id}".',
            }) + "\n"

        parent, child, other = "conv-parent", "conv-child", "conv-unrelated"
        make_brain(brain, parent, spawn_record(child))
        make_brain(brain, child, report_record(parent))
        make_brain(brain, other, json.dumps({"content": "unrelated work"}) + "\n")

        # --- classification -------------------------------------------------
        check("child is a delegate", classify(child, brain, STATE_DIR) == "delegate")
        check("parent is root DESPITE the child naming it in a report",
              classify(parent, brain, STATE_DIR) == "root")
        check("unrelated session is root", classify(other, brain, STATE_DIR) == "root")
        check("missing conversationId is unknown", classify("", brain, STATE_DIR) == "unknown")
        check("delegate verdict is cached",
              (STATE_DIR / f"{child}.json").exists())
        check("cached delegate survives an unreadable brain dir",
              classify(child, tmp / "nonexistent", STATE_DIR) == "delegate")
        check("root is NOT cached (a late parent flush must be able to flip it)",
              not (STATE_DIR / f"{parent}.json").exists())

        # The spawn marker and the id must co-occur in ONE record, not merely in the file.
        make_brain(brain, "conv-decoy",
                   json.dumps({"content": "Created the following subagents:"}) + "\n"
                   + json.dumps({"content": "unrelated mention of conv-victim"}) + "\n")
        check("marker and id in different records do not count",
              classify("conv-victim", brain, STATE_DIR) == "root")

        # A parent that flushes late must reclassify the child correctly.
        make_brain(brain, "conv-late-parent", "")
        check("child of a not-yet-flushed parent reads as root",
              classify("conv-late", brain, STATE_DIR) == "root")
        make_brain(brain, "conv-late-parent", spawn_record("conv-late"))
        check("same child reads as delegate once the parent flushes",
              classify("conv-late", brain, STATE_DIR) == "delegate")

        # --- source classification ------------------------------------------
        for path, expected in [
            ("feature/home/HomeScreen.kt", True),
            ("app/build.gradle.kts", True),
            ("app/src/main/res/values/strings.xml", True),
            (".agents/hooks/x.py", True),
            ("docs/omo-port/PLAN.md", False),
            ("notes.txt", False),
            ("package.json", False),
            ("README.md", False),
        ]:
            check(f"is_source({path}) == {expected}", is_source(path) is expected)

        # --- arg extraction -------------------------------------------------
        check("extracts TargetFile", extract_target({"TargetFile": "a/B.kt"}) == "a/B.kt")
        check("extracts a *_path key", extract_target({"file_path": "a/B.kt"}) == "a/B.kt")
        check("unknown arg shape yields None", extract_target({"blob": 3}) is None)

        # --- hook verdicts --------------------------------------------------
        deny = run_hook({
            "conversationId": parent,
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "feature/A.kt"}},
        })
        check("root writing Kotlin is denied", deny.get("decision") == "deny")
        check("denial names the executor", "executor" in (deny.get("reason") or ""))

        allow_child = run_hook({
            "conversationId": child,
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "feature/A.kt"}},
        })
        check("delegate writing Kotlin passes",
              allow_child.get("decision") == PASS_DECISION)

        allow_doc = run_hook({
            "conversationId": parent,
            "toolCall": {"name": "write_to_file", "args": {"TargetFile": "docs/notes.md"}},
        })
        check("root writing a doc passes", allow_doc.get("decision") == PASS_DECISION)

        check("unparseable arg shape passes",
              run_hook({"conversationId": parent,
                        "toolCall": {"name": "write_to_file", "args": {"weird": 1}}}
                       ).get("decision") == PASS_DECISION)
        check("missing conversationId passes",
              run_hook({"toolCall": {"name": "write_to_file",
                                     "args": {"TargetFile": "a.kt"}}}
                       ).get("decision") == PASS_DECISION)
        check("empty payload passes", run_hook({}).get("decision") == PASS_DECISION)

        # Scope: the invariant is about the project's code, not the agent's notepad.
        scratch = str(Path.home() / ".gemini" / "antigravity-cli" / "brain"
                      / "some-conv" / "scratch" / "notes.py")
        check("root writing outside the project passes",
              run_hook({"conversationId": parent,
                        "toolCall": {"name": "write_to_file",
                                     "args": {"TargetFile": scratch}}}
                       ).get("decision") == PASS_DECISION)
        check("root writing goals.json passes (ultrawork step 2)",
              run_hook({"conversationId": parent,
                        "toolCall": {"name": "write_to_file",
                                     "args": {"TargetFile": "goals.json"}}}
                       ).get("decision") == PASS_DECISION)

        # --- escape hatch ---------------------------------------------------
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OFF_SWITCH.write_text("off", encoding="utf-8")
        check("off switch lifts the gate",
              run_hook({"conversationId": parent,
                        "toolCall": {"name": "write_to_file",
                                     "args": {"TargetFile": "feature/A.kt"}}}
                       ).get("decision") == PASS_DECISION)
        OFF_SWITCH.unlink()
        check("gate returns after the off switch is removed",
              run_hook({"conversationId": parent,
                        "toolCall": {"name": "write_to_file",
                                     "args": {"TargetFile": "feature/A.kt"}}}
                       ).get("decision") == "deny")

        # --- garbage in -----------------------------------------------------
        import io
        stdin, stdout = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = io.StringIO("not json at all"), io.StringIO()
        try:
            hook_mode()
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = stdin, stdout
        check("garbage stdin still emits valid JSON",
              json.loads(out).get("decision") == PASS_DECISION)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all self-tests passed")
    return 0


def status_mode() -> int:
    print(f"off switch : {OFF_SWITCH} {'EXISTS (gate lifted)' if OFF_SWITCH.exists() else 'absent (gate active)'}")
    print(f"brain dir  : {BRAIN_DIR} {'ok' if BRAIN_DIR.is_dir() else 'MISSING'}")
    print(f"state dir  : {STATE_DIR}")
    if STATE_DIR.is_dir():
        cached = sorted(p.stem for p in STATE_DIR.glob("*.json"))
        print(f"delegates cached: {len(cached)}")
        for name in cached[:10]:
            print(f"  {name}")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return self_test()
    if "--status" in argv:
        return status_mode()
    if "--off" in argv:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OFF_SWITCH.write_text("off\n", encoding="utf-8")
        print(f"write guard lifted ({OFF_SWITCH}). Re-arm with --on.")
        return 0
    if "--on" in argv:
        OFF_SWITCH.unlink(missing_ok=True)
        print("write guard armed.")
        return 0
    hook_mode()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
