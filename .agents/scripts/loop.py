#!/usr/bin/env python3
"""Goal loop state for long-running agent work.

State lives under .agents/state/loop/<session>/:

    ledger.jsonl   append-only, the single source of truth
    goals.json     derived cache, rebuildable from the ledger alone

The ledger is the contract. `reconstruct` rebuilds goals.json from it and
`reconstruct --check` proves the two agree, which is what makes "a session is
fully reconstructable from the ledger" a testable claim rather than a hope.

Unlike the hook handlers in .agents/hooks/, this fails LOUD: it is a CLI an
agent calls, so a silent partial success would let the agent believe progress
was recorded when it was not. Non-zero exit plus a reason on stderr.

    python scripts/loop.py create-goals --brief "..." --goals-json goals.json
    python scripts/loop.py status --json
    python scripts/loop.py checkpoint --goal-id g1 --status complete \
        --evidence "gradlew :app:testDebugUnitTest -> 0" --command "..." --exit-code 0
    python scripts/loop.py steer --kind note --rationale "..."
    python scripts/loop.py reconstruct --check
    python scripts/loop.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATE_ROOT = Path(__file__).resolve().parent.parent / "state" / "loop"

GOAL_STATUSES = ("pending", "in_progress", "complete", "failed", "inconclusive")
CHECKPOINT_STATUSES = ("in_progress", "complete", "failed", "inconclusive")
STEER_KINDS = ("add-goal", "drop-goal", "revise", "note")

# An objective that names only an activity cannot fail, so it cannot finish.
ACTIVITY_ONLY = re.compile(
    r"^\s*(investigate|explore|look into|research|review|examine|study|"
    r"make progress|keep|continue|improve|clean up|work on|help with|"
    r"take a look)\b",
    re.IGNORECASE,
)
# Pass conditions that no input could falsify measure nothing.
UNFALSIFIABLE = re.compile(
    r"\b(works?\s+(correctly|properly|as expected|fine)|is\s+better|"
    r"looks?\s+(good|right|correct)|no\s+issues|properly\s+implemented|"
    r"is\s+improved|behaves\s+correctly)\b",
    re.IGNORECASE,
)


class LoopError(Exception):
    """Anything the caller did wrong, or any state we refuse to corrupt."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_session(explicit: str | None) -> str:
    for candidate in (
        explicit,
        os.environ.get("AGY_CONVERSATION_ID"),
        os.environ.get("ANTIGRAVITY_CONVERSATION_ID"),
    ):
        if candidate:
            return re.sub(r"[^A-Za-z0-9._-]", "_", candidate)
    return "default"


def session_dir(session: str, root: Path | None = None) -> Path:
    return (root or STATE_ROOT) / session


def ledger_path(session: str, root: Path | None = None) -> Path:
    return session_dir(session, root) / "ledger.jsonl"


def goals_path(session: str, root: Path | None = None) -> Path:
    return session_dir(session, root) / "goals.json"


# --------------------------------------------------------------------------
# ledger
# --------------------------------------------------------------------------


def read_ledger(session: str, root: Path | None = None) -> list[dict]:
    path = ledger_path(session, root)
    if not path.exists():
        return []
    events: list[dict] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise LoopError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
    return events


def append_event(session: str, kind: str, payload: dict, root: Path | None = None) -> dict:
    """Append one event. Never rewrites, never reorders."""
    directory = session_dir(session, root)
    directory.mkdir(parents=True, exist_ok=True)
    seq = len(read_ledger(session, root)) + 1
    event = {"seq": seq, "ts": now(), "kind": kind, **payload}
    with ledger_path(session, root).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


# --------------------------------------------------------------------------
# goal validation — the quality bar, enforced mechanically
# --------------------------------------------------------------------------


def validate_goal(goal: dict, index: int) -> list[str]:
    where = goal.get("id") or f"goals[{index}]"
    problems: list[str] = []

    objective = (goal.get("objective") or "").strip()
    if not objective:
        problems.append(f"{where}: objective is required")
    elif ACTIVITY_ONLY.match(objective):
        problems.append(
            f"{where}: objective names an activity, not an outcome "
            f"({objective.split()[0]!r}). State what will be TRUE when done."
        )

    if not (goal.get("stop_when") or "").strip():
        problems.append(
            f"{where}: stop_when is required — the observable state that ends this goal"
        )

    criteria = goal.get("criteria") or []
    if not criteria:
        problems.append(f"{where}: at least one success criterion is required")

    for c_index, criterion in enumerate(criteria):
        c_where = f"{where}.criteria[{criterion.get('id') or c_index}]"
        pass_condition = (criterion.get("pass_condition") or "").strip()
        if not pass_condition:
            problems.append(f"{c_where}: pass_condition is required")
        elif UNFALSIFIABLE.search(pass_condition):
            problems.append(
                f"{c_where}: pass_condition is not falsifiable ({pass_condition!r}). "
                "Name a binary observable."
            )
        if not (criterion.get("scenario") or "").strip():
            problems.append(
                f"{c_where}: scenario is required — the literal command, request, or action"
            )
        if not (criterion.get("expected_evidence") or "").strip():
            problems.append(
                f"{c_where}: expected_evidence is required — what artifact will prove it"
            )

    return problems


def normalise_goals(raw: object) -> list[dict]:
    if isinstance(raw, dict):
        raw = raw.get("goals", raw)
    if not isinstance(raw, list):
        raise LoopError("goals must be a JSON array of goal objects")

    goals: list[dict] = []
    problems: list[str] = []
    seen: set[str] = set()

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            problems.append(f"goals[{index}] is not an object")
            continue
        goal = {
            "id": (item.get("id") or f"g{index + 1}").strip(),
            "objective": (item.get("objective") or "").strip(),
            "deliverables": list(item.get("deliverables") or []),
            "criteria": [dict(c) for c in (item.get("criteria") or []) if isinstance(c, dict)],
            "constraints": list(item.get("constraints") or []),
            "stop_when": (item.get("stop_when") or "").strip(),
            "status": item.get("status") or "pending",
        }
        if goal["status"] not in GOAL_STATUSES:
            problems.append(f"{goal['id']}: status {goal['status']!r} not in {GOAL_STATUSES}")
        if goal["id"] in seen:
            problems.append(f"duplicate goal id {goal['id']!r}")
        seen.add(goal["id"])
        problems.extend(validate_goal(goal, index))
        goals.append(goal)

    if problems:
        raise LoopError("goal validation failed:\n  - " + "\n  - ".join(problems))
    return goals


def load_goals_argument(value: str) -> object:
    # utf-8-sig, not utf-8: PowerShell's `Out-File -Encoding utf8` writes a BOM, and an
    # agent handing us a file it just wrote that way is the common case on Windows.
    candidate = Path(value)
    text = candidate.read_text(encoding="utf-8-sig") if candidate.exists() else value
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LoopError(f"--goals-json is neither a readable file nor valid JSON: {exc}") from exc


# --------------------------------------------------------------------------
# derived state
# --------------------------------------------------------------------------


def reconstruct_state(events: list[dict]) -> dict:
    """Rebuild everything the loop knows from the ledger alone."""
    state: dict = {"brief": None, "goals": [], "ledger_seq": 0, "created_at": None}
    by_id: dict[str, dict] = {}

    for event in events:
        state["ledger_seq"] = max(state["ledger_seq"], event.get("seq", 0))
        kind = event.get("kind")

        if kind == "goals_created":
            state["brief"] = event.get("brief")
            state["created_at"] = event.get("ts")
            state["goals"] = []
            by_id = {}
            for goal in event.get("goals") or []:
                copy = dict(goal)
                copy.setdefault("evidence", [])
                state["goals"].append(copy)
                by_id[copy["id"]] = copy

        elif kind == "checkpoint":
            goal = by_id.get(event.get("goal_id"))
            if goal is None:
                continue
            goal["status"] = event.get("status", goal.get("status"))
            record = {
                "seq": event.get("seq"),
                "ts": event.get("ts"),
                "status": event.get("status"),
                "evidence": event.get("evidence"),
            }
            for optional in ("command", "exit_code", "evidence_paths"):
                if event.get(optional) is not None:
                    record[optional] = event[optional]
            goal.setdefault("evidence", []).append(record)

        elif kind == "steer":
            steer_kind = event.get("steer_kind")
            if steer_kind == "add-goal":
                for goal in event.get("goals") or []:
                    copy = dict(goal)
                    copy.setdefault("evidence", [])
                    state["goals"].append(copy)
                    by_id[copy["id"]] = copy
            elif steer_kind == "drop-goal":
                target = event.get("goal_id")
                state["goals"] = [g for g in state["goals"] if g["id"] != target]
                by_id.pop(target, None)
            elif steer_kind == "revise":
                goal = by_id.get(event.get("goal_id"))
                if goal is not None and isinstance(event.get("patch"), dict):
                    goal.update(event["patch"])

    return state


def write_goals_cache(session: str, state: dict, root: Path | None = None) -> Path:
    """Atomic write, so a crash can never leave a half-written cache."""
    path = goals_path(session, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
    )
    try:
        json.dump(state, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.close()
        os.replace(handle.name, path)
    except BaseException:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        raise
    return path


def refresh(session: str, root: Path | None = None) -> dict:
    state = reconstruct_state(read_ledger(session, root))
    write_goals_cache(session, state, root)
    return state


def progress_summary(state: dict) -> dict:
    goals = state.get("goals") or []
    done = [g for g in goals if g.get("status") == "complete"]
    active = next((g for g in goals if g.get("status") == "in_progress"), None)
    if active is None:
        active = next((g for g in goals if g.get("status") == "pending"), None)
    return {
        "total": len(goals),
        "complete": len(done),
        "failed": len([g for g in goals if g.get("status") == "failed"]),
        "active_goal": active["id"] if active else None,
        "all_complete": bool(goals) and len(done) == len(goals),
    }


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_create_goals(args, root: Path | None = None) -> int:
    session = resolve_session(args.session)
    existing = reconstruct_state(read_ledger(session, root))

    if existing.get("goals") and not args.force:
        summary = progress_summary(existing)
        if summary["all_complete"]:
            raise LoopError(
                f"session {session!r} already has {summary['total']} completed goals. "
                "Start unrelated work with --session <new-id>, or --force to overwrite."
            )
        raise LoopError(
            f"session {session!r} already has an active goal set "
            f"({summary['complete']}/{summary['total']} complete). "
            "Continue it, or use --session <new-id> for unrelated work."
        )

    brief = args.brief
    if args.brief_file:
        brief = Path(args.brief_file).read_text(encoding="utf-8-sig").strip()
    if not (brief or "").strip():
        raise LoopError("--brief or --brief-file is required")

    goals = normalise_goals(load_goals_argument(args.goals_json))
    append_event(session, "goals_created", {"brief": brief, "goals": goals}, root)
    state = refresh(session, root)
    emit(args, {"session": session, "created": len(goals), **progress_summary(state)})
    return 0


def cmd_status(args, root: Path | None = None) -> int:
    session = resolve_session(args.session)
    events = read_ledger(session, root)
    state = reconstruct_state(events)
    payload = {
        "session": session,
        "brief": state.get("brief"),
        "ledger_seq": state.get("ledger_seq", 0),
        "last_event": events[-1] if events else None,
        **progress_summary(state),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if not events:
        print(f"session {session}: no loop registered. Run create-goals first.")
        return 0
    print(f"session {session}  ledger_seq={payload['ledger_seq']}")
    print(f"brief: {payload['brief']}")
    print(f"progress: {payload['complete']}/{payload['total']} complete, "
          f"{payload['failed']} failed")
    for goal in state.get("goals") or []:
        marker = {"complete": "x", "failed": "!", "in_progress": ">"}.get(goal["status"], " ")
        print(f"  [{marker}] {goal['id']}  {goal['status']:<12} {goal['objective'][:70]}")
        for record in goal.get("evidence") or []:
            print(f"        seq {record['seq']}: {record['status']} - {record.get('evidence')}")
    if payload["all_complete"]:
        print("all goals complete - stop.")
    return 0


def cmd_checkpoint(args, root: Path | None = None) -> int:
    session = resolve_session(args.session)
    state = reconstruct_state(read_ledger(session, root))
    ids = {g["id"] for g in state.get("goals") or []}
    if not ids:
        raise LoopError(f"session {session!r} has no goals. Run create-goals first.")
    if args.goal_id not in ids:
        raise LoopError(f"unknown goal id {args.goal_id!r}. Known: {sorted(ids)}")
    if args.status != "in_progress" and not (args.evidence or "").strip():
        raise LoopError(
            f"--evidence is required for status {args.status!r}. "
            "A status without evidence is an assertion, not a checkpoint."
        )

    payload: dict = {
        "goal_id": args.goal_id,
        "status": args.status,
        "evidence": args.evidence,
    }
    if args.command:
        payload["command"] = args.command
    if args.exit_code is not None:
        payload["exit_code"] = args.exit_code
    if args.evidence_path:
        payload["evidence_paths"] = list(args.evidence_path)

    event = append_event(session, "checkpoint", payload, root)
    state = refresh(session, root)
    emit(args, {"session": session, "seq": event["seq"], **progress_summary(state)})
    return 0


def cmd_steer(args, root: Path | None = None) -> int:
    session = resolve_session(args.session)
    state = reconstruct_state(read_ledger(session, root))
    ids = {g["id"] for g in state.get("goals") or []}

    payload: dict = {"steer_kind": args.kind, "rationale": args.rationale}
    if args.evidence:
        payload["evidence"] = args.evidence

    if args.kind == "add-goal":
        if not args.goals_json:
            raise LoopError("--goals-json is required for --kind add-goal")
        added = normalise_goals(load_goals_argument(args.goals_json))
        clash = ids & {g["id"] for g in added}
        if clash:
            raise LoopError(f"goal ids already in use: {sorted(clash)}")
        payload["goals"] = added
    elif args.kind == "drop-goal":
        if args.goal_id not in ids:
            raise LoopError(f"unknown goal id {args.goal_id!r}. Known: {sorted(ids)}")
        payload["goal_id"] = args.goal_id
    elif args.kind == "revise":
        if args.goal_id not in ids:
            raise LoopError(f"unknown goal id {args.goal_id!r}. Known: {sorted(ids)}")
        if not args.patch_json:
            raise LoopError("--patch-json is required for --kind revise")
        patch = load_goals_argument(args.patch_json)
        if not isinstance(patch, dict):
            raise LoopError("--patch-json must be a JSON object")
        payload["goal_id"] = args.goal_id
        payload["patch"] = patch

    if not (args.rationale or "").strip():
        raise LoopError("--rationale is required: a steer without a reason is unreviewable")

    event = append_event(session, "steer", payload, root)
    state = refresh(session, root)
    emit(args, {"session": session, "seq": event["seq"], **progress_summary(state)})
    return 0


def cmd_reconstruct(args, root: Path | None = None) -> int:
    session = resolve_session(args.session)
    rebuilt = reconstruct_state(read_ledger(session, root))

    if args.check:
        path = goals_path(session, root)
        if not path.exists():
            raise LoopError(f"{path} does not exist — nothing to check against")
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached != rebuilt:
            raise LoopError(
                f"{path} does not match the ledger. The ledger is authoritative; "
                "run `reconstruct` without --check to rebuild."
            )
        emit(args, {"session": session, "match": True, **progress_summary(rebuilt)})
        return 0

    write_goals_cache(session, rebuilt, root)
    emit(args, {"session": session, "rebuilt": True, **progress_summary(rebuilt)})
    return 0


def emit(args, payload: dict) -> None:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(" ".join(f"{k}={v}" for k, v in payload.items()))


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------


def self_test() -> int:
    import shutil
    from types import SimpleNamespace

    root = Path(tempfile.mkdtemp(prefix="loop-selftest-"))
    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok   {name}")
        else:
            failures.append(f"{name}: {detail}")
            print(f"  FAIL {name} {detail}")

    def expect_error(name: str, fn, fragment: str) -> None:
        try:
            fn()
        except LoopError as exc:
            check(name, fragment.lower() in str(exc).lower(), f"got {exc!s}")
        else:
            check(name, False, "expected LoopError, none raised")

    good = [
        {
            "id": "g1",
            "objective": "The home screen reads its title from strings.xml.",
            "deliverables": ["feature/home/HomeScreen.kt", "app/src/main/res/values/strings.xml"],
            "criteria": [
                {
                    "id": "c1",
                    "pass_condition": "grep finds zero literal strings in Text() calls",
                    "scenario": "grep -n 'Text(\"' feature/home/HomeScreen.kt",
                    "expected_evidence": "empty grep output",
                }
            ],
            "constraints": ["do not touch the ViewModel"],
            "stop_when": "the grep is empty and the module compiles",
        }
    ]

    try:
        args = SimpleNamespace(
            session="s1", brief="extract strings", brief_file=None,
            goals_json=json.dumps(good), force=False, json=True,
        )
        check("create-goals accepts a well-formed goal", cmd_create_goals(args, root) == 0)

        expect_error(
            "create-goals refuses a second goal set",
            lambda: cmd_create_goals(args, root),
            "already has an active goal set",
        )

        expect_error(
            "rejects activity-only objective",
            lambda: normalise_goals([{**good[0], "objective": "Investigate the crash"}]),
            "activity, not an outcome",
        )
        expect_error(
            "rejects unfalsifiable pass_condition",
            lambda: normalise_goals([{
                **good[0],
                "criteria": [{**good[0]["criteria"][0], "pass_condition": "it works correctly"}],
            }]),
            "not falsifiable",
        )
        expect_error(
            "rejects missing stop_when",
            lambda: normalise_goals([{**good[0], "stop_when": ""}]),
            "stop_when is required",
        )
        expect_error(
            "rejects criterion without expected_evidence",
            lambda: normalise_goals([{
                **good[0],
                "criteria": [{"pass_condition": "exit code 0", "scenario": "./gradlew x"}],
            }]),
            "expected_evidence is required",
        )
        expect_error(
            "rejects goal with no criteria",
            lambda: normalise_goals([{**good[0], "criteria": []}]),
            "at least one success criterion",
        )
        expect_error(
            "rejects duplicate goal ids",
            lambda: normalise_goals([good[0], good[0]]),
            "duplicate goal id",
        )

        cp = SimpleNamespace(
            session="s1", goal_id="g1", status="complete",
            evidence="grep returned nothing; :feature:home compiled",
            command="./gradlew :feature:home:compileDebugKotlin", exit_code=0,
            evidence_path=["build/reports/compile.txt"], json=True,
        )
        check("checkpoint records evidence", cmd_checkpoint(cp, root) == 0)

        expect_error(
            "checkpoint rejects unknown goal",
            lambda: cmd_checkpoint(SimpleNamespace(**{**cp.__dict__, "goal_id": "nope"}), root),
            "unknown goal id",
        )
        expect_error(
            "checkpoint rejects complete without evidence",
            lambda: cmd_checkpoint(SimpleNamespace(**{**cp.__dict__, "evidence": " "}), root),
            "evidence is required",
        )

        state = reconstruct_state(read_ledger("s1", root))
        check("goal marked complete", state["goals"][0]["status"] == "complete")
        check("evidence carries the exit code",
              state["goals"][0]["evidence"][0]["exit_code"] == 0)
        check("progress reports all complete", progress_summary(state)["all_complete"] is True)

        st = SimpleNamespace(session="s1", json=True)
        check("status runs", cmd_status(st, root) == 0)
        check("status human-readable runs",
              cmd_status(SimpleNamespace(session="s1", json=False), root) == 0)

        # The acceptance criterion: goals.json is nothing but a cache of the ledger.
        rc = SimpleNamespace(session="s1", check=True, json=True)
        check("reconstruct --check matches the cache", cmd_reconstruct(rc, root) == 0)

        goals_path("s1", root).write_text('{"goals": []}\n', encoding="utf-8")
        expect_error(
            "reconstruct --check detects cache drift",
            lambda: cmd_reconstruct(rc, root),
            "does not match the ledger",
        )
        check("reconstruct repairs the cache",
              cmd_reconstruct(SimpleNamespace(session="s1", check=False, json=True), root) == 0)
        check("repaired cache matches ledger", cmd_reconstruct(rc, root) == 0)

        # Deleting the cache entirely must lose nothing.
        goals_path("s1", root).unlink()
        rebuilt = reconstruct_state(read_ledger("s1", root))
        check("full recovery from ledger alone",
              rebuilt["goals"][0]["status"] == "complete"
              and rebuilt["goals"][0]["evidence"][0]["command"].endswith("compileDebugKotlin"))

        steer = SimpleNamespace(
            session="s1", kind="add-goal", rationale="user added a second screen",
            evidence=None, goals_json=json.dumps([{**good[0], "id": "g2"}]),
            goal_id=None, patch_json=None, json=True,
        )
        check("steer add-goal appends", cmd_steer(steer, root) == 0)
        after = reconstruct_state(read_ledger("s1", root))
        check("added goal present", [g["id"] for g in after["goals"]] == ["g1", "g2"])
        check("earlier evidence survives a steer",
              after["goals"][0]["evidence"][0]["exit_code"] == 0)

        expect_error(
            "steer requires a rationale",
            lambda: cmd_steer(SimpleNamespace(**{**steer.__dict__, "rationale": "",
                                                 "kind": "note"}), root),
            "rationale is required",
        )

        drop = SimpleNamespace(session="s1", kind="drop-goal", rationale="descoped",
                               evidence=None, goals_json=None, goal_id="g2",
                               patch_json=None, json=True)
        check("steer drop-goal removes", cmd_steer(drop, root) == 0)
        check("dropped goal gone",
              [g["id"] for g in reconstruct_state(read_ledger("s1", root))["goals"]] == ["g1"])

        revise = SimpleNamespace(session="s1", kind="revise", rationale="tightened bound",
                                 evidence=None, goals_json=None, goal_id="g1",
                                 patch_json=json.dumps({"stop_when": "grep empty"}), json=True)
        check("steer revise patches", cmd_steer(revise, root) == 0)
        check("patch applied",
              reconstruct_state(read_ledger("s1", root))["goals"][0]["stop_when"] == "grep empty")

        seqs = [e["seq"] for e in read_ledger("s1", root)]
        check("ledger seq is dense and monotonic", seqs == list(range(1, len(seqs) + 1)),
              f"got {seqs}")

        check("status on unknown session is not an error",
              cmd_status(SimpleNamespace(session="never-used", json=True), root) == 0)

        # A goals file written by PowerShell's `Out-File -Encoding utf8` carries a BOM.
        bom_file = root / "bom-goals.json"
        bom_file.write_bytes(
            b"\xef\xbb\xbf" + json.dumps([{**good[0], "id": "b1"}]).encode("utf-8")
        )
        bom_args = SimpleNamespace(
            session="s-bom", brief="bom check", brief_file=None,
            goals_json=str(bom_file), force=False, json=True,
        )
        check("accepts a goals file with a UTF-8 BOM", cmd_create_goals(bom_args, root) == 0)

        # Non-ASCII must survive the round trip; a cp1252 console must not kill the run.
        uni = [{
            **good[0],
            "id": "u1",
            "objective": "Unicode round-trips — em-dash, ü, 日本語.",
        }]
        uni_args = SimpleNamespace(
            session="s-uni", brief="unicode — check", brief_file=None,
            goals_json=json.dumps(uni), force=False, json=True,
        )
        check("accepts non-ASCII goal text", cmd_create_goals(uni_args, root) == 0)
        check("status renders non-ASCII without raising",
              cmd_status(SimpleNamespace(session="s-uni", json=False), root) == 0)
        check("non-ASCII survives the ledger round trip",
              "日本語" in reconstruct_state(
                  read_ledger("s-uni", root))["goals"][0]["objective"])
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print()
    if failures:
        print(f"{len(failures)} failure(s):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all self-tests passed")
    return 0


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="loop.py", description="Goal loop state for long-running agent work."
    )
    parser.add_argument("--self-test", action="store_true", help="run the fixture suite and exit")
    subparsers = parser.add_subparsers(dest="command")

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--session", help="session id (default: $AGY_CONVERSATION_ID or 'default')")
        sub.add_argument("--json", action="store_true", help="machine-readable output")

    create = subparsers.add_parser("create-goals", help="register the goal set for a session")
    common(create)
    create.add_argument("--brief", help="the user's request, verbatim")
    create.add_argument("--brief-file", help="read the brief from a file instead")
    create.add_argument("--goals-json", required=True, help="JSON array of goals, or a path to one")
    create.add_argument("--force", action="store_true", help="overwrite an existing goal set")
    create.set_defaults(func=cmd_create_goals)

    status = subparsers.add_parser("status", help="what is done, what is next")
    common(status)
    status.set_defaults(func=cmd_status)

    checkpoint = subparsers.add_parser("checkpoint", help="record a goal outcome with evidence")
    common(checkpoint)
    checkpoint.add_argument("--goal-id", required=True)
    checkpoint.add_argument("--status", required=True, choices=CHECKPOINT_STATUSES)
    checkpoint.add_argument("--evidence", help="what was observed (required unless in_progress)")
    checkpoint.add_argument("--command", help="the command that produced the evidence")
    checkpoint.add_argument("--exit-code", type=int, help="that command's exit code")
    checkpoint.add_argument("--evidence-path", action="append",
                            help="path to an evidence artifact (repeatable)")
    checkpoint.set_defaults(func=cmd_checkpoint)

    steer = subparsers.add_parser("steer", help="change the goal set mid-run, on the record")
    common(steer)
    steer.add_argument("--kind", required=True, choices=STEER_KINDS)
    steer.add_argument("--rationale", help="why — required")
    steer.add_argument("--evidence", help="what prompted this")
    steer.add_argument("--goal-id", help="target goal for drop-goal / revise")
    steer.add_argument("--goals-json", help="goals to add, for add-goal")
    steer.add_argument("--patch-json", help="fields to overwrite, for revise")
    steer.set_defaults(func=cmd_steer)

    reconstruct = subparsers.add_parser(
        "reconstruct", help="rebuild goals.json from the ledger (--check verifies instead)"
    )
    common(reconstruct)
    reconstruct.add_argument("--check", action="store_true",
                             help="fail if the cache disagrees with the ledger")
    reconstruct.set_defaults(func=cmd_reconstruct)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Goal text is user-supplied and will contain non-ASCII. A cp1252 console would
    # raise UnicodeEncodeError mid-print, after the ledger write has already happened.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, OSError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2

    try:
        return args.func(args)
    except LoopError as exc:
        print(f"loop: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"loop: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
