#!/usr/bin/env python3
"""PreInvocation gate: turn the word "ultrawork" in a prompt into an actual directive.

`PreInvocation` carries **no prompt text**, so the transcript is the only source. It also
fires ~50× per session, in every agent in the tree — so the whole design here is about
being cheap and firing exactly once per triggering prompt.

**How it stays cheap.** The transcript is append-only, so this keeps a byte offset per
conversation and only ever scans what was appended since the last invocation. The common
case (nothing appended) is a single `stat`. A turn's worth of tool output is a few KB. Only
the first invocation of a conversation reads the whole file.

**How it fires once.** A trigger only counts if it appears in the *last* user record of the
scanned region — which, because the region is by definition the newest bytes, means the
current turn's prompt. Records are fingerprinted (`created_at` + request text), and a
fingerprint that already fired never fires again.

**Three ways it deliberately stands down:**

  1. The trigger word is matched **only inside `<USER_REQUEST>`**, never in the
     `<ADDITIONAL_METADATA>` block that follows it — that block inlines whole skill bodies
     when a slash command is used, and matching there would fire on any skill that happens
     to mention the word.
  2. If the same record shows the platform already activated the skill
     (`The user has explicitly invoked the (ultrawork) skill`), there is nothing to do —
     `/ultrawork` loads the skill natively, because skills, not workflows, are Antigravity's
     slash-command mechanism.
  3. Records carrying this hook's own marker are skipped, so an injection can never
     re-trigger the gate that wrote it.

**Scope.** Keying on a literal word scopes this to the main session for free: a subagent's
task prompt cannot contain the trigger unless the orchestrator deliberately put it there —
in which case firing inside the worker is the intended behaviour, not a leak.

Narrow on purpose: the gate matches keywords only. The fuzzy cases ("do this properly", "no
shortcuts") are what the skill's own `description` is for — Antigravity discovers skills
semantically, and a regex that tried to cover intent would fire on prose about rigour.

    python hooks/intent_gate.py              # hook mode, reads a PreInvocation payload
    python hooks/intent_gate.py --self-test
    python hooks/intent_gate.py --status
    python hooks/intent_gate.py --print-directive
    python hooks/intent_gate.py --scan <transcript.jsonl>   # what would fire, and why not
    python hooks/intent_gate.py --off / --on
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
AGENTS_DIR = HOOKS_DIR.parent
STATE_DIR = AGENTS_DIR / "state" / "intent_gate"
OFF_SWITCH = STATE_DIR / "off"

SKILL_NAME = "ultrawork"
SKILL_PATH = ".agents/skills/ultrawork/SKILL.md"

# Deliberately literal. Anything fuzzier belongs in the skill's description, where
# Antigravity's own semantic discovery can weigh it. The optional separator covers
# "ultrawork" too, so there is no separate branch for it.
TRIGGER = re.compile(r"\b(ultra[-\s]?work|ulw)\b", re.IGNORECASE)

USER_REQUEST = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL)
PLATFORM_ACTIVATION = f"invoked the ({SKILL_NAME}) skill"

# Present in every injection, and skipped when scanning, so the gate cannot feed itself.
MARKER = "<ultrawork-mode>"

# Runaway backstop only — the fingerprint set is what actually prevents re-firing. Set high
# enough that a real session cannot hit it by asking for ultrawork repeatedly, because the
# cap silences the gate with no signal the user can see.
MAX_ACTIVATIONS = 25
FIRST_SCAN_CAP = 8 * 1024 * 1024
DELTA_SCAN_CAP = 2 * 1024 * 1024
HEAD_BYTES = 256          # enough to tell one transcript from another

DIRECTIVE = f"""{MARKER}
Ultrawork is on for this request. Open your reply with `ultrawork:` and one line naming what
you are about to do.

1. Read `{SKILL_PATH}` now with view_file and follow it for the rest of this
   request. That file is the authority; this notice is only the trigger.
2. Classify the request first — research / investigation / evaluation / fix / implementation —
   and say which in one line. "Look into", "explain" and "what do you think" are not requests
   to change code.
3. Register the run with `python .agents/scripts/loop.py create-goals` before the first edit.
   The goals are the contract, and the Stop gate will hold you to them.
4. Delegate: `explore` for discovery (2-3 in one invoke_subagent call), `oracle` for
   judgement, `worker-quick` / `worker-deep` for edits. Verify what they return.
5. Prove the result with a command and its exit code. Completeness, not maximalism — being
   asked for rigour is not permission to widen the scope, and lean still governs how much
   code exists.

Do not repeat this notice back to the user.
</ultrawork-mode>"""


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------


def state_path(conversation_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in conversation_id)
    return STATE_DIR / f"{safe or 'unknown'}.json"


def read_state(conversation_id: str) -> dict:
    # Deliberately not an atomic write on the other side: a torn state file degrades to
    # "scan from the start, arm at most once more", which is cheap and harmless. Paying
    # loop.py's tempfile+os.replace dance here would buy nothing.
    try:
        loaded = json.loads(state_path(conversation_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    loaded.setdefault("offset", 0)
    loaded.setdefault("fired", [])
    return loaded


def write_state(conversation_id: str, state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_path(conversation_id).write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


# --------------------------------------------------------------------------
# transcript reading
# --------------------------------------------------------------------------


def user_request_text(content: str) -> str:
    """Just the human's words. Never the metadata block that follows them."""
    match = USER_REQUEST.search(content)
    if match:
        return match.group(1)
    # No wrapper: a record shape we have not seen. Fall back to the whole content, which is
    # the conservative choice only because <ADDITIONAL_METADATA> cannot be present either.
    return content if "<ADDITIONAL_METADATA>" not in content else ""


def fingerprint(record: dict, request: str) -> str:
    raw = f"{record.get('created_at', '')}|{request.strip()}"
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:12]


def find_trigger(chunk: str) -> tuple[dict | None, str]:
    """(the triggering record, why nothing fired). Last match in the chunk wins."""
    reason = "no new user prompt in this region"
    hit: dict | None = None

    for line in chunk.splitlines():
        line = line.strip()
        if not line or '"USER_INPUT"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue  # a partial first line from an offset read
        if record.get("type") != "USER_INPUT" or record.get("source") != "USER_EXPLICIT":
            continue

        content = record.get("content") or ""
        if MARKER in content:
            continue  # our own injection, echoed back

        request = user_request_text(content)
        if not TRIGGER.search(request):
            hit, reason = None, "user prompt carries no trigger word"
            continue
        if PLATFORM_ACTIVATION in content:
            hit, reason = None, f"/{SKILL_NAME} already loaded the skill natively"
            continue

        hit = {"record": record, "request": request,
               "fingerprint": fingerprint(record, request)}
        reason = ""

    return hit, reason


def file_head(path: Path) -> str | None:
    """Fingerprint of the first bytes — identity of the file behind the path."""
    try:
        with path.open("rb") as handle:
            return hashlib.sha1(handle.read(HEAD_BYTES)).hexdigest()[:12]
    except OSError:
        return None


def scan(transcript_path: str, offset: int, head: str | None = None
         ) -> tuple[dict | None, str, int, str | None]:
    """Read only what was appended. Returns (hit, reason, new offset, head)."""
    path = Path(transcript_path)
    try:
        size = path.stat().st_size
    except OSError:
        return None, "transcript not readable", offset, head

    # A stored offset only means anything if the same file is still behind the path.
    # Size alone cannot tell you that: a rotated transcript can be the same length.
    head_now = file_head(path)
    if head_now is None:
        return None, "transcript not readable", offset, head
    if head is not None and head_now != head:
        offset = 0
    if size < offset:
        offset = 0
    if size == offset and offset:
        return None, "transcript unchanged since the last invocation", offset, head_now

    cap = FIRST_SCAN_CAP if offset == 0 else DELTA_SCAN_CAP
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(min(size - offset, cap))
    except OSError:
        return None, "transcript not readable", offset, head_now

    # Advance only to the last complete record. Two things slice a line otherwise — a
    # half-flushed append, and the scan cap — and an offset that steps past the cut
    # discards that record for good. A sliced *user* record would silently swallow the
    # prompt the gate exists to catch.
    complete = data.rfind(b"\n") + 1
    if not complete:
        return None, "no complete record appended yet", offset, head_now

    hit, reason = find_trigger(data[:complete].decode("utf-8", "replace"))
    return hit, reason, offset + complete, head_now


# --------------------------------------------------------------------------
# hook mode
# --------------------------------------------------------------------------


def hook_mode() -> None:
    directive = None
    note = ""
    try:
        if OFF_SWITCH.exists():
            print("{}")
            return

        payload = json.loads(sys.stdin.read() or "{}")
        transcript = payload.get("transcriptPath")
        conversation_id = payload.get("conversationId") or ""
        if not transcript:
            print("{}")
            return

        state = read_state(conversation_id)
        hit, reason, new_offset, head = scan(
            transcript, int(state.get("offset") or 0), state.get("head")
        )
        if new_offset != state.get("offset") or head != state.get("head"):
            state["offset"], state["head"] = new_offset, head
            write_state(conversation_id, state)

        if hit is None:
            note = reason
        elif hit["fingerprint"] in state["fired"]:
            note = "already armed for this prompt"
        elif len(state["fired"]) >= MAX_ACTIVATIONS:
            note = f"activation cap reached ({MAX_ACTIVATIONS} this conversation)"
        else:
            state["fired"].append(hit["fingerprint"])
            state["last_armed"] = time.time()
            write_state(conversation_id, state)
            directive = DIRECTIVE
            note = f"armed on {hit['fingerprint']}"
    except Exception as exc:  # fail open: never break a turn over our own bug
        print(f"intent_gate: {type(exc).__name__}: {exc}", file=sys.stderr)

    if note:
        print(f"intent_gate: {note}", file=sys.stderr)
    if directive:
        print(json.dumps({"injectSteps": [{"ephemeralMessage": directive}]}))
    else:
        print("{}")


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def self_test() -> int:
    import io
    import shutil
    import tempfile

    global STATE_DIR, OFF_SWITCH
    tmp = Path(tempfile.mkdtemp(prefix="intent-gate-selftest-"))
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok   {name}")
        else:
            failures.append(f"{name}: {detail}")
            print(f"  FAIL {name} {detail}")

    # Shapes copied from real transcripts, 2026-08-27. The metadata block matters: a slash
    # command inlines the whole skill body there, which is why the trigger is only ever
    # matched inside <USER_REQUEST>.
    def user_record(request: str, metadata: str = "", ts: str = "2026-08-27T07:06:10Z") -> str:
        content = f"<USER_REQUEST>\n{request}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\n" \
                  f"The current local time is: 2026-08-27T14:06:10+07:00.\n{metadata}\n" \
                  f"</ADDITIONAL_METADATA>"
        return json.dumps({"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT",
                           "status": "DONE", "created_at": ts, "content": content}) + "\n"

    def model_record(text: str = "thinking about it") -> str:
        return json.dumps({"step_index": 1, "source": "MODEL", "type": "GENERIC",
                           "status": "DONE", "created_at": "2026-08-27T07:06:13Z",
                           "content": text}) + "\n"

    def append(path: Path, *records: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(record)

    def run_hook(transcript: Path, conversation_id: str = "conv-1") -> dict:
        stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr
        sys.stdin = io.StringIO(json.dumps({
            "conversationId": conversation_id,
            "transcriptPath": str(transcript),
            "invocationNum": 1,
            "workspacePaths": [str(tmp)],
            "modelName": "gemini-3.7-flash-high",
        }))
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        try:
            hook_mode()
            return json.loads(sys.stdout.getvalue())
        finally:
            sys.stdin, sys.stdout, sys.stderr = stdin, stdout, stderr

    def armed(verdict: dict) -> bool:
        steps = verdict.get("injectSteps") or []
        return bool(steps) and MARKER in (steps[0].get("ephemeralMessage") or "")

    try:
        STATE_DIR = tmp / "state"
        OFF_SWITCH = STATE_DIR / "off"

        # --- the trigger, and firing exactly once ---------------------------
        tr = tmp / "t1.jsonl"
        append(tr, user_record("ultrawork this: extract the strings in HomeScreen.kt"))
        first = run_hook(tr)
        check("a prompt containing the trigger arms the gate", armed(first))
        check("the directive names the skill file", SKILL_PATH in
              first["injectSteps"][0]["ephemeralMessage"])
        check("the directive is an ephemeralMessage",
              "ephemeralMessage" in first["injectSteps"][0])

        check("a second invocation with nothing appended does not re-arm",
              not armed(run_hook(tr)))
        append(tr, model_record(), model_record("more tool output"))
        check("appended model output does not re-arm", not armed(run_hook(tr)))
        append(tr, user_record("thanks, now do the settings screen",
                              ts="2026-08-27T07:10:00Z"))
        check("a follow-up prompt without the trigger does not arm",
              not armed(run_hook(tr)))
        append(tr, user_record("ulw: and the profile screen too",
                              ts="2026-08-27T07:12:00Z"))
        check("a later prompt with the trigger arms again", armed(run_hook(tr)))

        # --- trigger vocabulary --------------------------------------------
        for index, phrase in enumerate([
            "ultrawork this", "ULTRAWORK", "ultra work please", "ultra-work it",
            "ulw", "let's ultrawork the migration",
        ]):
            path = tmp / f"vocab{index}.jsonl"
            append(path, user_record(phrase))
            check(f"trigger: {phrase!r}", armed(run_hook(path, f"conv-v{index}")))

        for index, phrase in enumerate([
            "just do the ultra minimal thing",
            "ultraworkish",
            "fix the ULWX config parser",
            "update the workflow",
            "do this properly and thoroughly, no shortcuts",
        ]):
            path = tmp / f"neg{index}.jsonl"
            append(path, user_record(phrase))
            check(f"no trigger: {phrase!r}", not armed(run_hook(path, f"conv-n{index}")))

        # --- the metadata trap ---------------------------------------------
        # A slash command inlines the invoked skill's whole body into the metadata
        # block. If that body says "ultrawork" anywhere, matching the raw record would
        # fire on an unrelated skill.
        trap = tmp / "trap.jsonl"
        append(trap, user_record(
            "/code-review look at the diff",
            metadata="/code-review is a [Slash Command]:\n<SKILL>The user has explicitly "
                     "invoked the (code-review) skill. ... see also the ultrawork skill for "
                     "maximum rigour ...</SKILL>",
        ))
        check("a trigger word inside <ADDITIONAL_METADATA> does not arm",
              not armed(run_hook(trap, "conv-trap")))

        # --- platform already did it ----------------------------------------
        native = tmp / "native.jsonl"
        append(native, user_record(
            "/ultrawork rebuild the home screen",
            metadata="/ultrawork is a [Slash Command]:\n<SKILL>The user has explicitly "
                     f"invoked the ({SKILL_NAME}) skill. You must strictly follow the "
                     "instructions in this skill.</SKILL>",
        ))
        check("the gate stands down when /ultrawork loaded the skill natively",
              not armed(run_hook(native, "conv-native")))

        # --- it cannot feed itself ------------------------------------------
        echo = tmp / "echo.jsonl"
        append(echo, json.dumps({
            "type": "USER_INPUT", "source": "USER_EXPLICIT", "created_at": "x",
            "content": f"<USER_REQUEST>\n{DIRECTIVE}\n</USER_REQUEST>",
        }) + "\n")
        check("a record echoing our own injection does not arm",
              not armed(run_hook(echo, "conv-echo")))

        # --- record filtering -----------------------------------------------
        wrong = tmp / "wrong.jsonl"
        append(wrong, json.dumps({
            "type": "GENERIC", "source": "MODEL", "created_at": "x",
            "content": "<USER_REQUEST>ultrawork</USER_REQUEST>",
        }) + "\n")
        check("a MODEL record is not a user prompt", not armed(run_hook(wrong, "conv-wrong")))

        implicit = tmp / "implicit.jsonl"
        append(implicit, json.dumps({
            "type": "USER_INPUT", "source": "USER_IMPLICIT", "created_at": "x",
            "content": "<USER_REQUEST>ultrawork</USER_REQUEST>",
        }) + "\n")
        check("a non-explicit USER_INPUT is ignored",
              not armed(run_hook(implicit, "conv-implicit")))

        # --- caps and hatches ------------------------------------------------
        cap = tmp / "cap.jsonl"
        conv = "conv-cap"
        armed_count = 0
        for turn in range(MAX_ACTIVATIONS + 3):
            append(cap, user_record(f"ultrawork turn {turn}", ts=f"2026-08-27T08:{turn:02d}:00Z"))
            if armed(run_hook(cap, conv)):
                armed_count += 1
        check(f"activations are capped at {MAX_ACTIVATIONS}", armed_count == MAX_ACTIVATIONS,
              f"got {armed_count}")

        hatch = tmp / "hatch.jsonl"
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OFF_SWITCH.write_text("off", encoding="utf-8")
        append(hatch, user_record("ultrawork this"))
        check("the off switch silences the gate", not armed(run_hook(hatch, "conv-hatch")))
        OFF_SWITCH.unlink()
        check("the gate returns once the switch is removed",
              armed(run_hook(hatch, "conv-hatch")))

        # --- robustness -------------------------------------------------------
        # Found by a delegated /code-review of this file, 2026-08-27: an offset that
        # advanced past a half-written line discarded that record for good, so a prompt
        # caught mid-flush was swallowed silently.
        split = tmp / "split.jsonl"
        record = user_record("ultrawork the migration", ts="2026-08-27T11:00:00Z")
        with split.open("wb") as handle:
            handle.write(record[: len(record) // 2].encode("utf-8"))  # mid-flush
        check("a half-written record does not arm yet",
              not armed(run_hook(split, "conv-split")))
        with split.open("ab") as handle:
            handle.write(record[len(record) // 2:].encode("utf-8"))  # flush completes
        check("the same record arms once it is complete",
              armed(run_hook(split, "conv-split")))

        check("a missing transcript path fails open",
              not armed(run_hook(tmp / "nope.jsonl", "conv-missing")))

        junk = tmp / "junk.jsonl"
        junk.write_text("not json\n{\"partial\": \n", encoding="utf-8")
        check("unparseable transcript lines are skipped",
              not armed(run_hook(junk, "conv-junk")))

        truncated = tmp / "trunc.jsonl"
        append(truncated, user_record("ultrawork one", ts="2026-08-27T09:00:00Z"))
        run_hook(truncated, "conv-trunc")
        truncated.write_text("", encoding="utf-8")  # rotation
        append(truncated, user_record("ultrawork two", ts="2026-08-27T09:05:00Z"))
        check("a rotated transcript is rescanned from the start",
              armed(run_hook(truncated, "conv-trunc")))

        stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr
        sys.stdin = io.StringIO("this is not json")
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        try:
            hook_mode()
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout, sys.stderr = stdin, stdout, stderr
        check("garbage stdin still emits valid JSON", json.loads(out) == {})

        sys.stdin, sys.stdout = io.StringIO("{}"), io.StringIO()
        try:
            hook_mode()
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = stdin, stdout
        check("an empty payload emits a no-op", json.loads(out) == {})

        # --- the directive itself ---------------------------------------------
        check("the directive is short enough to inject every turn",
              len(DIRECTIVE.splitlines()) <= 30, f"{len(DIRECTIVE.splitlines())} lines")
        check("the directive tells the agent to classify intent",
              "Classify" in DIRECTIVE)
        check("the directive points at the loop CLI", "loop.py create-goals" in DIRECTIVE)
        check("the directive carries the marker", DIRECTIVE.startswith(MARKER))
        skill_file = AGENTS_DIR / "skills" / SKILL_NAME / "SKILL.md"
        check("the skill the directive names exists", skill_file.is_file(), str(skill_file))
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


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def scan_mode(path: str) -> int:
    hit, reason, offset, _ = scan(path, 0)
    print(f"transcript : {path}")
    print(f"bytes read : {offset}")
    if hit:
        print(f"WOULD ARM  : fingerprint {hit['fingerprint']}")
        print(f"on prompt  : {hit['request'].strip()[:200]}")
    else:
        print(f"would not arm: {reason}")
    return 0


def status_mode() -> int:
    print(f"off switch : {OFF_SWITCH} "
          f"{'EXISTS (gate silent)' if OFF_SWITCH.exists() else 'absent (gate active)'}")
    print(f"skill      : {AGENTS_DIR / 'skills' / SKILL_NAME / 'SKILL.md'}")
    print(f"triggers   : {TRIGGER.pattern}")
    if not STATE_DIR.is_dir():
        print("no state yet — the gate has not seen a conversation.")
        return 0
    for path in sorted(STATE_DIR.glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        print(f"\n{path.stem}")
        print(f"  scanned  : {state.get('offset')} bytes")
        print(f"  armed    : {len(state.get('fired') or [])} {state.get('fired')}")
    return 0


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            pass

    if "--self-test" in argv:
        return self_test()
    if "--status" in argv:
        return status_mode()
    if "--print-directive" in argv:
        print(DIRECTIVE)
        return 0
    if "--scan" in argv:
        index = argv.index("--scan")
        if index + 1 >= len(argv):
            print("--scan needs a transcript path", file=sys.stderr)
            return 2
        return scan_mode(argv[index + 1])
    if "--off" in argv:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OFF_SWITCH.write_text("off\n", encoding="utf-8")
        print(f"intent gate silenced ({OFF_SWITCH}). Re-arm with --on.")
        return 0
    if "--on" in argv:
        OFF_SWITCH.unlink(missing_ok=True)
        print("intent gate armed.")
        return 0
    hook_mode()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
