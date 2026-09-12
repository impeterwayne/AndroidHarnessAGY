#!/usr/bin/env python3
"""Stop hook: hold a registered loop open until its goals hold — brakes first.

`Stop` -> `{"decision": "continue", "reason": ...}` blocks termination and re-enters
the agent loop with `reason` injected. That is a loaded gun: a continuation rule with
no brakes spins forever and bills for it. So the brakes come first and the
verification is deliberately cheap.

**Scope.** This hook does nothing unless the stopping conversation *owns a goal loop*
under `.agents/state/loop/`. No loop, no opinion — which is also what keeps it from
fighting subagents, since a delegate does not own its parent's loop. Ownership is
opt-in by construction: someone had to run `loop.py create-goals` first.

**What it checks** (in this order — every one of these exits by *permitting* the stop):

  1. off switch present                        -> permit
  2. no loop owned by this conversation        -> permit
  3. terminationReason is not a real stop      -> permit, counters untouched
  4. hard stop (error / cancel / budget caps)  -> permit
  5. `fullyIdle` is false — work in flight     -> permit, counters untouched
  6. this loop is already marked stuck         -> permit
  7. inside a failure cooldown                 -> permit
  8. no goals, or all complete and the record  -> permit  <- the good exit
     holds up
  9. three consecutive failed checkpoints      -> permit (the SKILL's own stop rule)
 10. the ledger did not advance since the      -> mark stuck, permit
     last resume
 11. resume budget spent (2/goal, 6/session)   -> permit
 else                                          -> continue, with the goal, its
                                                  criteria, and the exact
                                                  checkpoint command

**Verification validates the record, it does not re-run the work.** Hooks block the
agent loop synchronously against a 30s default timeout, and a Gradle build costs
30–90s. So the agent runs the build via `run_command` and records the outcome
(`--command`, `--exit-code`, `--evidence-path`); this hook checks the *recorded* exit
code, that the named artifacts exist, and that `goals.json` still agrees with the
ledger. Cheap, and it catches the failure that matters: "marked complete" sitting on
top of a command that exited non-zero.

**Divergence from PLAN.md, on purpose.** The plan said to suppress entirely on
context pressure. But the loop exists *precisely* to survive compaction — the skill's
first instruction after context loss is `loop.py status --json`. Suppressing would
throw away the mechanism at the moment it earns its keep. Instead compaction tightens
the per-goal budget to one resume and leads the injected reason with "read your status
first". An amnesiac that then does nothing is caught by the ledger-advance check.

Platform facts worth not re-deriving (read out of `agy.exe`, 2026-08-27):

  - Real `terminationReason` values are the `TERMINATION_REASON_*` enum minus its
    prefix — `NO_TOOL_CALL` for a normal model stop, not the docs' `model_stop`.
  - The runtime already caps stop-hook continuations
    (`CascadeExecutorConfig.max_stop_hook_continuations`, changelog: "after a
    configurable number of consecutive continuations, the hook can no longer block").
    The value is not ours to read, so it is a backstop, not the brake.
  - `$ANTIGRAVITY_CONVERSATION_ID` **is** injected into `run_command`'s environment and
    it equals the hook payload's `conversationId` (live-verified). So loop.py's state
    directory is named after the conversation, and `resolve_session`'s first branch is
    the normal path; the transcript-adoption branch is the safety net, not the plan.

Verified live 2026-08-27 (Antigravity CLI 1.1.22, `gemini-3.7-flash-high`), driven
through herdr against a two-goal loop:

  - The block lands in the child's own transcript as a `SYSTEM_MESSAGE`/`SYSTEM`
    record, prefixed by the runtime with `Stop hook blocked termination: ` — so this
    hook's `reason` should read as a standalone instruction, not as a sentence
    continuation.
  - Told to answer and stop with an unfinished goal, the agent was resumed once, did
    the work, checkpointed with `--command`/`--exit-code`, and the next Stop permitted
    ("all goals complete, evidence holds"). One resume, no churn.
  - Given a deliberately unsatisfiable goal, it resumed once, ran the scenario, and
    checkpointed `failed` with the exit code — which closed the loop out on the record
    and let the session end. The designed exit is cheaper than the resume cap.

    python hooks/stop_verifier.py             # hook mode, reads a Stop payload
    python hooks/stop_verifier.py --self-test
    python hooks/stop_verifier.py --status
    python hooks/stop_verifier.py --off / --on
    python hooks/stop_verifier.py --clear [--session <id>]
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

# Proven safe: probe.py returned exactly this on 4 real Stop events and every
# session terminated normally. Anything other than "continue" permits the stop.
PERMIT = {"decision": "stop"}

HOOKS_DIR = Path(__file__).resolve().parent
AGENTS_DIR = HOOKS_DIR.parent
REPO_DIR = AGENTS_DIR.parent

LOOP_ROOT = AGENTS_DIR / "state" / "loop"
STATE_DIR = AGENTS_DIR / "state" / "stop_verifier"
OFF_SWITCH = STATE_DIR / "off"
LOOP_CLI = AGENTS_DIR / "scripts" / "loop.py"

MAX_RESUMES_PER_GOAL = 2
MAX_RESUMES_PER_GOAL_COMPACTED = 1
MAX_RESUMES_PER_SESSION = 6
CONSECUTIVE_FAILURE_LIMIT = 3  # matches skills/loop/SKILL.md's own stop rule
COOLDOWN_BASE_S = 30           # doubles per consecutive failure

# terminationReason, prefix-stripped. A stop we are willing to reverse:
RESUMABLE_REASONS = {"", "NO_TOOL_CALL", "TERMINAL_STEP_TYPE", "UNSPECIFIED"}
# Not a real termination — the loop is already continuing. Touch nothing.
IGNORED_REASONS = {"EARLY_CONTINUE", "INJECTED_RESPONSE"}
# Everything else (ERROR, USER_CANCELED, MAX_INVOCATIONS, MAX_FORCED_INVOCATIONS,
# MAX_TOKEN_BUDGET_EXCEEDED, HALTED_STEP, TERMINAL_CUSTOM_HOOK) hard-stops.

# Verbatim from agy.exe: the notice injected when history is dropped for length.
COMPACTION_MARKER = b"earlier parts of this conversation have been truncated"
TRANSCRIPT_SCAN_CAP = 8 * 1024 * 1024

SESSION_FLAG = re.compile(rb"--session[= ]+([A-Za-z0-9._-]+)")
LOOP_CLI_MARKER = b"loop.py"


# --------------------------------------------------------------------------
# ledger access — borrowed from loop.py so the semantics have one definition
# --------------------------------------------------------------------------


def loop_module():
    """Import scripts/loop.py. Its ledger logic is the contract; don't restate it."""
    spec = importlib.util.spec_from_file_location("agy_loop", LOOP_CLI)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {LOOP_CLI}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sanitize(session: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", session or "")


def loop_state(session: str, loop=None) -> dict:
    loop = loop or loop_module()
    return loop.reconstruct_state(loop.read_ledger(session, LOOP_ROOT))


# --------------------------------------------------------------------------
# which loop, if any, belongs to this conversation
# --------------------------------------------------------------------------


def has_ledger(session: str) -> bool:
    return bool(session) and (LOOP_ROOT / session / "ledger.jsonl").is_file()


def claim_path(session: str) -> Path:
    return STATE_DIR / "claims" / f"{sanitize(session)}.json"


def claimed_by(session: str) -> str | None:
    try:
        return json.loads(claim_path(session).read_text(encoding="utf-8")).get("conversationId")
    except (OSError, ValueError):
        return None


def claim(session: str, conversation_id: str) -> None:
    try:
        path = claim_path(session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"session": session, "conversationId": conversation_id, "ts": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        pass


def transcript_mentions_loop(transcript_path: str | None) -> tuple[bool, str | None]:
    """(did this conversation drive loop.py, the last --session it named).

    The bridge for the one loose joint in step 6: loop.py names its state directory
    after `$ANTIGRAVITY_CONVERSATION_ID` (which the CLI does inject into run_command
    env — the literal `ANTIGRAVITY_CONVERSATION_ID=%s` appears in agy.exe's command
    runner) and falls back to 'default' if it is absent. So the directory name usually
    *is* the conversationId, but "usually" is not a foundation for a gate.
    """
    if not transcript_path:
        return False, None
    try:
        data = Path(transcript_path).read_bytes()[:TRANSCRIPT_SCAN_CAP]
    except OSError:
        return False, None
    # Searched as bytes: a transcript is megabytes and decoding it to find one
    # substring is the whole cost of this branch.
    if LOOP_CLI_MARKER not in data:
        return False, None
    named = SESSION_FLAG.findall(data)
    return True, named[-1].decode("ascii", "ignore") if named else None


def any_loop_registered() -> bool:
    """Cheapest possible early exit: nobody has ever run create-goals here."""
    if not LOOP_ROOT.is_dir():
        return False
    return any(LOOP_ROOT.glob("*/ledger.jsonl"))


def resolve_session(payload: dict) -> tuple[str | None, str]:
    """Which loop directory this stopping conversation owns, and how we decided."""
    if not any_loop_registered():
        return None, "no loops registered"

    conversation_id = sanitize(payload.get("conversationId") or "")
    if conversation_id and has_ledger(conversation_id):
        return conversation_id, "conversationId"

    for var in ("ANTIGRAVITY_CONVERSATION_ID", "AGY_CONVERSATION_ID"):
        candidate = sanitize(os.environ.get(var) or "")
        if candidate and has_ledger(candidate):
            return candidate, f"${var}"

    drove_loop, named = transcript_mentions_loop(payload.get("transcriptPath"))
    if not drove_loop:
        return None, "no loop"

    for candidate, how in ((sanitize(named or ""), "--session in transcript"),
                           ("default", "adopted 'default'")):
        if not has_ledger(candidate):
            continue
        owner = claimed_by(candidate)
        if owner and owner != conversation_id:
            continue  # another conversation got there first
        if conversation_id:
            claim(candidate, conversation_id)
        return candidate, how

    return None, "no loop"


# --------------------------------------------------------------------------
# per-conversation hook state
# --------------------------------------------------------------------------


def state_path(conversation_id: str) -> Path:
    return STATE_DIR / f"{sanitize(conversation_id) or 'unknown'}.json"


def read_state(conversation_id: str) -> dict:
    try:
        loaded = json.loads(state_path(conversation_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        loaded = {}
    loaded.setdefault("resumes", [])
    loaded.setdefault("per_goal", {})
    loaded.setdefault("stuck", None)
    loaded.setdefault("cooldown_until", 0)
    return loaded


def write_state(conversation_id: str, state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_path(conversation_id).write_text(
            json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


# --------------------------------------------------------------------------
# evidence validation — check the record, never re-run the work
# --------------------------------------------------------------------------


def evidence_root(payload: dict) -> Path:
    paths = payload.get("workspacePaths") or []
    if paths and isinstance(paths[0], str):
        return Path(paths[0])
    return REPO_DIR


def completing_records(goal: dict) -> list[dict]:
    return [r for r in goal.get("evidence") or [] if r.get("status") == "complete"]


def trailing_failures(goal: dict) -> int:
    count = 0
    for record in reversed(goal.get("evidence") or []):
        if record.get("status") == "failed":
            count += 1
        elif record.get("status") in ("complete", "in_progress", "inconclusive"):
            break
    return count


def evidence_problems(state: dict, root: Path, session: str, loop=None) -> list[str]:
    """What the ledger itself says is wrong with the claims made in it."""
    problems: list[str] = []

    for goal in state.get("goals") or []:
        if goal.get("status") != "complete":
            continue
        records = completing_records(goal)
        if not records:
            problems.append(
                f"{goal['id']}: status is complete but no completing checkpoint is recorded"
            )
            continue
        last = records[-1]
        code = last.get("exit_code")
        if isinstance(code, int) and code != 0:
            problems.append(
                f"{goal['id']}: marked complete, but the recorded command exited {code}"
                f" ({last.get('command')})"
            )
        for artifact in last.get("evidence_paths") or []:
            candidate = Path(artifact)
            if not candidate.is_absolute():
                candidate = root / artifact
            if not candidate.exists():
                problems.append(f"{goal['id']}: recorded evidence artifact is missing: {artifact}")

    # goals.json is only a cache of the ledger, so drift means someone hand-edited
    # state. The ledger wins; say so rather than silently trusting either.
    if state.get("goals") and loop is not None:
        cache = LOOP_ROOT / session / "goals.json"
        try:
            if cache.is_file() and json.loads(cache.read_text(encoding="utf-8")) != state:
                problems.append(
                    "goals.json disagrees with the ledger — run "
                    "`python .agents/scripts/loop.py reconstruct`"
                )
        except (OSError, ValueError):
            problems.append(f"{cache} is unreadable — run `loop.py reconstruct`")

    return problems


# --------------------------------------------------------------------------
# the decision
# --------------------------------------------------------------------------


def reason_text(facts: dict, resume_index: int, budget: int) -> str:
    session = facts["session"]
    progress = facts["progress"]
    lines: list[str] = []

    if facts["compacted"]:
        lines.append(
            "Your context was truncated. Run "
            "`python .agents/scripts/loop.py status --json` before anything else, and "
            "resume from what it reports — do not re-plan and do not redo a completed goal."
        )
        lines.append("")

    if facts["problems"]:
        lines.append(
            f"Loop {session}: every goal is marked complete, but the recorded evidence "
            "does not support that:"
        )
        lines.extend(f"  - {problem}" for problem in facts["problems"])
        lines.append("")
        lines.append(
            "Either fix the work and checkpoint again, or correct the record with "
            "`--status failed` / `--status inconclusive` and say what happened."
        )
    else:
        goal = facts["active"] or {}
        lines.append(
            f"Loop {session} is not finished: {progress['complete']}/{progress['total']} "
            f"goals complete, {progress['failed']} failed."
        )
        lines.append(f"Active goal {goal.get('id')}: {goal.get('objective')}")
        if goal.get("stop_when"):
            lines.append(f"  stop_when: {goal['stop_when']}")
        for criterion in goal.get("criteria") or []:
            lines.append(
                f"  [{criterion.get('id') or '?'}] {criterion.get('pass_condition')}"
            )
            if criterion.get("scenario"):
                lines.append(f"        run: {criterion['scenario']}")
        for constraint in goal.get("constraints") or []:
            lines.append(f"  constraint: {constraint}")
        lines.append("")
        lines.append("Run the scenarios, then record the outcome:")
        lines.append(
            f"  python .agents/scripts/loop.py checkpoint --goal-id {goal.get('id')} "
            "--status complete --evidence \"<what you observed>\" "
            "--command \"<command>\" --exit-code 0"
        )
        lines.append(
            "If a scenario cannot be run at all, checkpoint it `inconclusive` with why; "
            "if it ran and failed, `failed`. Either one ends the goal on the record."
        )

    lines.append("")
    lines.append(
        f"(stop_verifier: resume {resume_index} of {budget} for this goal. "
        "To stop being held open, close the goals out on the record — or run "
        "`python .agents/hooks/stop_verifier.py --off`.)"
    )
    return "\n".join(lines)


def decide(facts: dict, hook_state: dict, now: float) -> tuple[dict, dict, str]:
    """(verdict, hook_state, one-line note). Every early return permits the stop."""
    reason = facts["termination"]

    if reason in IGNORED_REASONS:
        return PERMIT, hook_state, f"not a termination ({reason})"
    if facts["error"]:
        return PERMIT, hook_state, f"hard stop: error {facts['error'][:120]!r}"
    if reason not in RESUMABLE_REASONS:
        return PERMIT, hook_state, f"hard stop: terminationReason {reason}"
    if not facts["fully_idle"]:
        # Children or steps still in flight. Another Stop follows when they finish;
        # resuming now would race them.
        return PERMIT, hook_state, "not fully idle — work still in flight"
    if hook_state.get("stuck"):
        return PERMIT, hook_state, f"loop marked stuck: {hook_state['stuck']}"
    if now < hook_state.get("cooldown_until", 0):
        remaining = int(hook_state["cooldown_until"] - now)
        return PERMIT, hook_state, f"in failure cooldown for another {remaining}s"

    progress = facts["progress"]
    if not progress["total"]:
        return PERMIT, hook_state, "loop has no goals"
    if progress["all_complete"] and not facts["problems"]:
        return PERMIT, hook_state, "all goals complete, evidence holds"
    if not progress["all_complete"] and facts["active"] is None:
        # Every remaining goal is failed or inconclusive: the record is closed out.
        return PERMIT, hook_state, "no goal left to work — all outcomes recorded"

    goal_key = (facts["active"] or {}).get("id") or "__evidence__"

    if facts["consecutive_failures"] >= CONSECUTIVE_FAILURE_LIMIT:
        return PERMIT, hook_state, (
            f"{goal_key} has {facts['consecutive_failures']} consecutive failed "
            "checkpoints — surfacing rather than grinding"
        )

    resumes = hook_state["resumes"]
    if resumes and resumes[-1].get("ledger_seq") == facts["ledger_seq"]:
        hook_state["stuck"] = (
            f"ledger did not advance past seq {facts['ledger_seq']} after a resume"
        )
        return PERMIT, hook_state, hook_state["stuck"]

    budget = (
        MAX_RESUMES_PER_GOAL_COMPACTED if facts["compacted"] else MAX_RESUMES_PER_GOAL
    )
    used = int(hook_state["per_goal"].get(goal_key, 0))
    if used >= budget:
        return PERMIT, hook_state, f"resume budget spent for {goal_key} ({used}/{budget})"
    if len(resumes) >= MAX_RESUMES_PER_SESSION:
        return PERMIT, hook_state, (
            f"session resume budget spent ({len(resumes)}/{MAX_RESUMES_PER_SESSION})"
        )

    hook_state["per_goal"][goal_key] = used + 1
    hook_state["resumes"].append({
        "ts": now,
        "ledger_seq": facts["ledger_seq"],
        "goal_id": goal_key,
        "compacted": facts["compacted"],
    })
    failures = facts["consecutive_failures"]
    if failures:
        hook_state["cooldown_until"] = now + COOLDOWN_BASE_S * (2 ** (failures - 1))

    verdict = {
        "decision": "continue",
        "reason": reason_text(facts, used + 1, budget),
    }
    return verdict, hook_state, f"continue: {goal_key} (resume {used + 1}/{budget})"


# --------------------------------------------------------------------------
# hook mode
# --------------------------------------------------------------------------


def gather_facts(payload: dict, session: str, loop=None) -> dict:
    state = loop_state(session, loop)
    progress = loop.progress_summary(state) if loop else {}
    active_id = progress.get("active_goal")
    active = next((g for g in state.get("goals") or [] if g["id"] == active_id), None)
    compacted = False
    transcript = payload.get("transcriptPath")
    if transcript:
        try:
            compacted = COMPACTION_MARKER in Path(transcript).read_bytes()[:TRANSCRIPT_SCAN_CAP]
        except OSError:
            compacted = False

    raw_reason = str(payload.get("terminationReason") or "")
    return {
        "session": session,
        "termination": raw_reason.upper().replace("TERMINATION_REASON_", ""),
        "error": str(payload.get("error") or ""),
        # Absent means "nothing said it was busy" — treat as idle, or a payload
        # variant without the field would mute the hook completely.
        "fully_idle": bool(payload.get("fullyIdle", True)),
        "ledger_seq": int(state.get("ledger_seq") or 0),
        "progress": progress,
        "active": active,
        "consecutive_failures": trailing_failures(active) if active else 0,
        "compacted": compacted,
        "problems": evidence_problems(state, evidence_root(payload), session, loop),
    }


def hook_mode() -> None:
    verdict = PERMIT
    note = ""
    try:
        if OFF_SWITCH.exists():
            print(json.dumps(PERMIT))
            return

        payload = json.loads(sys.stdin.read() or "{}")
        conversation_id = payload.get("conversationId") or ""
        session, how = resolve_session(payload)
        if session is None:
            print(json.dumps(PERMIT))
            return

        loop = loop_module()
        facts = gather_facts(payload, session, loop)
        hook_state = read_state(conversation_id)
        hook_state["session"] = session
        hook_state["binding"] = how
        verdict, hook_state, note = decide(facts, hook_state, time.time())
        hook_state["last_note"] = note
        hook_state["last_seen_ledger_seq"] = facts["ledger_seq"]
        write_state(conversation_id, hook_state)
    except Exception as exc:  # fail open: a stuck agent beats a wrong verdict
        print(f"stop_verifier: {type(exc).__name__}: {exc}", file=sys.stderr)
        verdict = PERMIT
    if note:
        print(f"stop_verifier: {note}", file=sys.stderr)
    print(json.dumps(verdict))


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def self_test() -> int:  # noqa: C901 - a flat fixture list reads better than helpers
    import io
    import shutil
    import tempfile

    global LOOP_ROOT, STATE_DIR, OFF_SWITCH
    tmp = Path(tempfile.mkdtemp(prefix="stop-verifier-selftest-"))
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok   {name}")
        else:
            failures.append(f"{name}: {detail}")
            print(f"  FAIL {name} {detail}")

    def goal(gid: str = "g1", **over) -> dict:
        base = {
            "id": gid,
            "objective": "The home screen reads its title from strings.xml.",
            "deliverables": ["feature/home/HomeScreen.kt"],
            "criteria": [{
                "id": "c1",
                "pass_condition": ":feature:home compiles, exit code 0",
                "scenario": "./gradlew :feature:home:compileDebugKotlin",
                "expected_evidence": "exit code 0 recorded in the checkpoint",
            }],
            "constraints": ["do not touch HomeViewModel"],
            "stop_when": "the module compiles",
            "status": "pending",
        }
        base.update(over)
        return base

    def make_loop(session: str, goals: list[dict], checkpoints=()) -> None:
        loop.append_event(session, "goals_created",
                          {"brief": "extract strings", "goals": goals}, LOOP_ROOT)
        for cp in checkpoints:
            loop.append_event(session, "checkpoint", cp, LOOP_ROOT)
        loop.write_goals_cache(session, loop_state(session, loop), LOOP_ROOT)

    def stop_payload(session: str, **over) -> dict:
        payload = {
            "conversationId": session,
            "terminationReason": "NO_TOOL_CALL",
            "error": "",
            "fullyIdle": True,
            "executionNum": 0,
            "workspacePaths": [str(tmp / "ws")],
            "modelName": "gemini-3.7-flash-high",
        }
        payload.update(over)
        return payload

    def run_hook(payload: dict) -> dict:
        stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr
        sys.stdin = io.StringIO(json.dumps(payload))
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        try:
            hook_mode()
            return json.loads(sys.stdout.getvalue())
        finally:
            sys.stdin, sys.stdout, sys.stderr = stdin, stdout, stderr

    def facts_for(session: str, payload: dict | None = None) -> dict:
        return gather_facts(payload or stop_payload(session), session, loop)

    try:
        LOOP_ROOT = tmp / "loop"
        STATE_DIR = tmp / "hookstate"
        OFF_SWITCH = STATE_DIR / "off"
        (tmp / "ws").mkdir()
        loop = loop_module()

        # ------------------------------------------------------------------
        # the payload vocabulary is the runtime's, not the docs'
        # ------------------------------------------------------------------
        make_loop("open", [goal()])
        check("real NO_TOOL_CALL stop is resumable",
              run_hook(stop_payload("open")).get("decision") == "continue")
        make_loop("prefixed", [goal()])
        check("prefixed TERMINATION_REASON_NO_TOOL_CALL is normalised",
              run_hook(stop_payload("prefixed",
                                    terminationReason="TERMINATION_REASON_NO_TOOL_CALL")
                       ).get("decision") == "continue")
        for hard in ("ERROR", "USER_CANCELED", "MAX_INVOCATIONS",
                     "MAX_FORCED_INVOCATIONS", "MAX_TOKEN_BUDGET_EXCEEDED",
                     "HALTED_STEP", "TERMINAL_CUSTOM_HOOK"):
            shutil.rmtree(STATE_DIR, ignore_errors=True)
            check(f"{hard} hard-stops",
                  run_hook(stop_payload("open", terminationReason=hard)
                           ).get("decision") != "continue")
        for ignored in ("EARLY_CONTINUE", "INJECTED_RESPONSE"):
            shutil.rmtree(STATE_DIR, ignore_errors=True)
            check(f"{ignored} is not treated as a termination",
                  run_hook(stop_payload("open", terminationReason=ignored)
                           ).get("decision") != "continue")
            check(f"{ignored} spends no resume budget",
                  read_state("open")["per_goal"] == {})
        shutil.rmtree(STATE_DIR, ignore_errors=True)
        check("a non-empty error hard-stops",
              run_hook(stop_payload("open", error="context deadline exceeded")
                       ).get("decision") != "continue")
        check("fullyIdle=false defers instead of racing children",
              run_hook(stop_payload("open", fullyIdle=False)).get("decision") != "continue")
        shutil.rmtree(STATE_DIR, ignore_errors=True)

        # ------------------------------------------------------------------
        # scope: no loop, no opinion
        # ------------------------------------------------------------------
        check("a conversation with no loop is left alone",
              run_hook(stop_payload("no-loop-here")).get("decision") != "continue")
        check("empty payload permits", run_hook({}).get("decision") != "continue")

        # ------------------------------------------------------------------
        # THE ACCEPTANCE TEST: nothing loops more than twice
        # ------------------------------------------------------------------
        make_loop("cap", [goal()])
        seen = []
        for turn in range(6):
            verdict = run_hook(stop_payload("cap"))
            seen.append(verdict.get("decision"))
            if verdict.get("decision") == "continue":
                # the agent did *something* recordable, so the ledger advances
                loop.append_event("cap", "checkpoint",
                                  {"goal_id": "g1", "status": "in_progress",
                                   "evidence": f"turn {turn}"}, LOOP_ROOT)
                loop.write_goals_cache("cap", loop_state("cap", loop), LOOP_ROOT)
        check("a productive-but-unfinished loop resumes at most twice",
              seen.count("continue") <= MAX_RESUMES_PER_GOAL, f"got {seen}")
        check("and then permits the stop for good", seen[-1] != "continue", f"got {seen}")

        # ------------------------------------------------------------------
        # stuck detection is ledger progress, not turn count
        # ------------------------------------------------------------------
        make_loop("stuck", [goal()])
        first = run_hook(stop_payload("stuck"))
        second = run_hook(stop_payload("stuck"))
        check("first stop on an idle-but-unfinished loop resumes",
              first.get("decision") == "continue")
        check("a resume that produced no ledger entry is stuck, not resumed again",
              second.get("decision") != "continue")
        check("stuck is recorded", bool(read_state("stuck").get("stuck")))
        check("stuck is sticky", run_hook(stop_payload("stuck")).get("decision") != "continue")

        # ------------------------------------------------------------------
        # the good exit
        # ------------------------------------------------------------------
        (tmp / "ws" / "compile.txt").write_text("ok", encoding="utf-8")
        make_loop("done", [goal()], [{
            "goal_id": "g1", "status": "complete",
            "evidence": ":feature:home compiled clean",
            "command": "./gradlew :feature:home:compileDebugKotlin",
            "exit_code": 0, "evidence_paths": ["compile.txt"],
        }])
        check("all goals complete with valid evidence permits the stop",
              run_hook(stop_payload("done")).get("decision") != "continue")

        # ------------------------------------------------------------------
        # verification validates the record
        # ------------------------------------------------------------------
        make_loop("lying", [goal()], [{
            "goal_id": "g1", "status": "complete", "evidence": "looks fine to me",
            "command": "./gradlew :feature:home:compileDebugKotlin", "exit_code": 1,
        }])
        verdict = run_hook(stop_payload("lying"))
        check("complete on a non-zero exit code is not accepted",
              verdict.get("decision") == "continue")
        check("the reason names the exit code", "exited 1" in (verdict.get("reason") or ""))

        make_loop("ghost", [goal()], [{
            "goal_id": "g1", "status": "complete", "evidence": "built",
            "command": "./gradlew x", "exit_code": 0,
            "evidence_paths": ["build/reports/nope.txt"],
        }])
        verdict = run_hook(stop_payload("ghost"))
        check("a missing evidence artifact is not accepted",
              verdict.get("decision") == "continue")
        check("the reason names the artifact", "nope.txt" in (verdict.get("reason") or ""))

        make_loop("drift", [goal()], [{
            "goal_id": "g1", "status": "complete", "evidence": "built",
            "command": "./gradlew x", "exit_code": 0,
        }])
        (LOOP_ROOT / "drift" / "goals.json").write_text('{"goals": []}', encoding="utf-8")
        check("cache drift is reported",
              "goals.json disagrees" in (run_hook(stop_payload("drift")).get("reason") or ""))

        # An absolute evidence path must be honoured as given.
        artifact = tmp / "abs-evidence.txt"
        artifact.write_text("x", encoding="utf-8")
        make_loop("abs", [goal()], [{
            "goal_id": "g1", "status": "complete", "evidence": "built",
            "command": "./gradlew x", "exit_code": 0,
            "evidence_paths": [str(artifact)],
        }])
        check("an absolute evidence path resolves",
              run_hook(stop_payload("abs")).get("decision") != "continue")

        # ------------------------------------------------------------------
        # closed-out records end the loop
        # ------------------------------------------------------------------
        make_loop("given-up", [goal()], [{
            "goal_id": "g1", "status": "failed", "evidence": "compile fails upstream",
        }])
        check("a goal recorded failed is not reopened",
              run_hook(stop_payload("given-up")).get("decision") != "continue")

        make_loop("grind", [goal(status="pending")], [
            {"goal_id": "g1", "status": "in_progress", "evidence": "start"},
            {"goal_id": "g1", "status": "failed", "evidence": "attempt 1"},
            {"goal_id": "g1", "status": "failed", "evidence": "attempt 2"},
            {"goal_id": "g1", "status": "failed", "evidence": "attempt 3"},
        ])
        # reconstruct leaves the goal 'failed', so re-open it to isolate the
        # consecutive-failure rule from the closed-record rule.
        loop.append_event("grind", "steer",
                          {"steer_kind": "revise", "goal_id": "g1",
                           "rationale": "reopened", "patch": {"status": "in_progress"}},
                          LOOP_ROOT)
        loop.write_goals_cache("grind", loop_state("grind", loop), LOOP_ROOT)
        check("three consecutive failures stops instead of grinding",
              run_hook(stop_payload("grind")).get("decision") != "continue")
        check("trailing failures are counted, not all failures",
              facts_for("grind")["consecutive_failures"] == 3)

        make_loop("recovered", [goal()], [
            {"goal_id": "g1", "status": "failed", "evidence": "attempt 1"},
            {"goal_id": "g1", "status": "failed", "evidence": "attempt 2"},
            {"goal_id": "g1", "status": "in_progress", "evidence": "new approach"},
        ])
        check("a later in_progress checkpoint resets the failure streak",
              facts_for("recovered")["consecutive_failures"] == 0)

        # ------------------------------------------------------------------
        # cooldown after a failure
        # ------------------------------------------------------------------
        make_loop("cooldown", [goal()], [
            {"goal_id": "g1", "status": "failed", "evidence": "attempt 1"},
        ])
        loop.append_event("cooldown", "steer",
                          {"steer_kind": "revise", "goal_id": "g1", "rationale": "retry",
                           "patch": {"status": "in_progress"}}, LOOP_ROOT)
        loop.write_goals_cache("cooldown", loop_state("cooldown", loop), LOOP_ROOT)
        check("a resume after a failure still happens",
              run_hook(stop_payload("cooldown")).get("decision") == "continue")
        check("but it arms a cooldown", read_state("cooldown")["cooldown_until"] > time.time())
        loop.append_event("cooldown", "checkpoint",
                          {"goal_id": "g1", "status": "in_progress", "evidence": "work"},
                          LOOP_ROOT)
        loop.write_goals_cache("cooldown", loop_state("cooldown", loop), LOOP_ROOT)
        check("the cooldown suppresses the next resume",
              run_hook(stop_payload("cooldown")).get("decision") != "continue")

        # ------------------------------------------------------------------
        # compaction tightens the budget instead of muting the loop
        # ------------------------------------------------------------------
        transcript = tmp / "compacted.jsonl"
        transcript.write_text(json.dumps({
            "type": "SYSTEM_MESSAGE", "source": "SYSTEM",
            "content": " **The earlier parts of this conversation have been truncated "
                       "due to its long length. The following content summarizes the "
                       "truncated context so that you may continue your work. **",
        }) + "\n", encoding="utf-8")
        make_loop("amnesia", [goal()])
        payload = stop_payload("amnesia", transcriptPath=str(transcript))
        check("compaction is detected from the transcript", facts_for("amnesia", payload)["compacted"])
        verdict = run_hook(payload)
        check("a compacted session still gets one resume",
              verdict.get("decision") == "continue")
        check("and the reason leads with reading its own status",
              "status --json" in (verdict.get("reason") or "").split("\n")[0])
        loop.append_event("amnesia", "checkpoint",
                          {"goal_id": "g1", "status": "in_progress", "evidence": "work"},
                          LOOP_ROOT)
        loop.write_goals_cache("amnesia", loop_state("amnesia", loop), LOOP_ROOT)
        check("but only one", run_hook(payload).get("decision") != "continue")

        # ------------------------------------------------------------------
        # session binding
        # ------------------------------------------------------------------
        make_loop("default", [goal()])
        driver = tmp / "driver.jsonl"
        driver.write_text(json.dumps({
            "type": "GENERIC", "source": "MODEL",
            "content": "python .agents/scripts/loop.py status --json",
        }) + "\n", encoding="utf-8")
        session, how = resolve_session({"conversationId": "conv-a",
                                        "transcriptPath": str(driver)})
        check("a conversation that drove loop.py adopts 'default'", session == "default", how)
        check("adoption is claimed", claimed_by("default") == "conv-a")
        session2, _ = resolve_session({"conversationId": "conv-b",
                                       "transcriptPath": str(driver)})
        check("a second conversation cannot adopt a claimed loop", session2 is None)

        make_loop("explicit-session", [goal()])
        named = tmp / "named.jsonl"
        named.write_text(json.dumps({
            "content": "python .agents/scripts/loop.py checkpoint --session explicit-session "
                       "--goal-id g1 --status in_progress",
        }) + "\n", encoding="utf-8")
        session3, _ = resolve_session({"conversationId": "conv-c", "transcriptPath": str(named)})
        check("--session in the transcript wins", session3 == "explicit-session")

        quiet = tmp / "quiet.jsonl"
        quiet.write_text(json.dumps({"content": "no loop here"}) + "\n", encoding="utf-8")
        check("a conversation that never touched loop.py adopts nothing",
              resolve_session({"conversationId": "conv-d",
                               "transcriptPath": str(quiet)})[0] is None)

        make_loop("conv-env", [goal()])
        os.environ["ANTIGRAVITY_CONVERSATION_ID"] = "conv-env"
        try:
            check("$ANTIGRAVITY_CONVERSATION_ID is a fallback binding",
                  resolve_session({"conversationId": "unknown-id"})[0] == "conv-env")
        finally:
            del os.environ["ANTIGRAVITY_CONVERSATION_ID"]

        # ------------------------------------------------------------------
        # escape hatches and failure modes
        # ------------------------------------------------------------------
        make_loop("hatch", [goal()])
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OFF_SWITCH.write_text("off", encoding="utf-8")
        check("the off switch permits every stop",
              run_hook(stop_payload("hatch")).get("decision") != "continue")
        OFF_SWITCH.unlink()
        check("the gate returns once the switch is removed",
              run_hook(stop_payload("hatch")).get("decision") == "continue")

        stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr
        sys.stdin = io.StringIO("this is not json")
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        try:
            hook_mode()
            out = sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout, sys.stderr = stdin, stdout, stderr
        check("garbage stdin still emits a valid permit",
              json.loads(out).get("decision") != "continue")

        corrupt = LOOP_ROOT / "corrupt"
        (corrupt).mkdir(parents=True, exist_ok=True)
        (corrupt / "ledger.jsonl").write_text("{not json\n", encoding="utf-8")
        check("an unreadable ledger fails open",
              run_hook(stop_payload("corrupt")).get("decision") != "continue")

        empty = LOOP_ROOT / "empty"
        empty.mkdir(parents=True, exist_ok=True)
        (empty / "ledger.jsonl").write_text("", encoding="utf-8")
        check("a registered-but-empty loop permits",
              run_hook(stop_payload("empty")).get("decision") != "continue")
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


def status_mode() -> int:
    print(f"off switch : {OFF_SWITCH} "
          f"{'EXISTS (gate lifted)' if OFF_SWITCH.exists() else 'absent (gate active)'}")
    print(f"loop root  : {LOOP_ROOT} {'ok' if LOOP_ROOT.is_dir() else 'MISSING'}")
    sessions = sorted(p.parent.name for p in LOOP_ROOT.glob("*/ledger.jsonl")) \
        if LOOP_ROOT.is_dir() else []
    print(f"loops      : {len(sessions)} {sessions[:10]}")

    if not STATE_DIR.is_dir():
        print("no hook state yet — nothing has stopped under this gate.")
        return 0
    for path in sorted(STATE_DIR.glob("*.json")):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cooldown = state.get("cooldown_until", 0)
        print(f"\n{path.stem}")
        print(f"  session    : {state.get('session')} ({state.get('binding')})")
        print(f"  resumes    : {len(state.get('resumes') or [])} {state.get('per_goal')}")
        print(f"  stuck      : {state.get('stuck')}")
        print(f"  cooldown   : {max(0, int(cooldown - time.time()))}s remaining")
        print(f"  last note  : {state.get('last_note')}")
    return 0


def clear_mode(argv: list[str]) -> int:
    target = None
    if "--session" in argv:
        index = argv.index("--session")
        if index + 1 < len(argv):
            target = sanitize(argv[index + 1])
    if not STATE_DIR.is_dir():
        print("nothing to clear.")
        return 0
    cleared = 0
    for path in list(STATE_DIR.glob("*.json")):
        if target:
            try:
                if json.loads(path.read_text(encoding="utf-8")).get("session") != target:
                    continue
            except (OSError, ValueError):
                continue
        path.unlink(missing_ok=True)
        cleared += 1
    print(f"cleared {cleared} counter file(s)"
          + (f" for session {target}" if target else "")
          + ". Resume budgets and stuck flags are reset.")
    return 0


def main(argv: list[str]) -> int:
    # Goal text is user-supplied and will contain non-ASCII; a cp1252 console would
    # otherwise mangle --status output. Hook stdout stays ASCII regardless, because
    # json.dumps escapes by default.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            pass

    if "--self-test" in argv:
        return self_test()
    if "--status" in argv:
        return status_mode()
    if "--clear" in argv:
        return clear_mode(argv)
    if "--off" in argv:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OFF_SWITCH.write_text("off\n", encoding="utf-8")
        print(f"stop verifier lifted ({OFF_SWITCH}). Re-arm with --on.")
        return 0
    if "--on" in argv:
        OFF_SWITCH.unlink(missing_ok=True)
        print("stop verifier armed.")
        return 0
    hook_mode()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
