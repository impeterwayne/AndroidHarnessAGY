---
name: loop
description: Durable goal loop for long-running work — decompose a request into evidence-bound goals, record progress in an append-only ledger, and survive context loss or compaction without re-planning. Use when the user asks for a loop, durable or checkpointed execution, evidence-led work, or when a task is large enough that losing your place would be expensive.
metadata:
  short-description: Evidence-bound goal loop with an append-only ledger
---

# loop

State lives under `.agents/state/loop/<session>/`. Drive it with `run_command`:

```bash
python .agents/scripts/loop.py <subcommand> [flags]
```

Two files per session. **`ledger.jsonl` is append-only and authoritative.**
`goals.json` is only a cache of it — never hand-edit either. If they ever disagree,
the ledger wins and `reconstruct` repairs the cache.

The CLI fails loud: non-zero exit and a reason on stderr. Read the error, fix the
input, retry. Do not work around it by writing state files yourself.

## After any context loss, do this first

```bash
python .agents/scripts/loop.py status --json
```

Then resume from what it reports. **Never re-plan from scratch and never redo a goal
already marked complete** — the ledger already holds the evidence.

## 1. Register goals, before any edit

```bash
python .agents/scripts/loop.py create-goals \
  --brief "<the user's request, verbatim>" \
  --goals-json goals.json --json
```

The goal set is the binding contract for the run, so its quality caps the run's
quality. The CLI rejects goals that fall below the bar — see "The quality bar" below
for what it enforces and why.

Goal shape:

```json
[
  {
    "id": "g1",
    "objective": "Home screen reads every visible string from strings.xml.",
    "deliverables": ["feature/home/HomeScreen.kt", "app/src/main/res/values/strings.xml"],
    "criteria": [
      {
        "id": "c1",
        "pass_condition": "grep finds zero string literals inside Text() calls",
        "scenario": "grep -n 'Text(\"' feature/home/HomeScreen.kt",
        "expected_evidence": "empty grep output"
      },
      {
        "id": "c2",
        "pass_condition": ":feature:home compiles, exit code 0",
        "scenario": "./gradlew :feature:home:compileDebugKotlin",
        "expected_evidence": "exit code 0 recorded in the checkpoint"
      }
    ],
    "constraints": ["do not touch HomeViewModel", "assumed: en-only, no new locales — reversible"],
    "stop_when": "the grep is empty and the module compiles"
  }
]
```

One goal per outcome. If the request contains two genuinely independent outcomes,
register two goals — not one goal with a compound objective.

`create-goals` refuses to overwrite an existing goal set. For unrelated new work use
`--session <new-id>`; use `--force` only when you deliberately mean to discard
recorded evidence.

## The quality bar

The CLI enforces these mechanically, so a rejected goal is a real defect in the goal,
not a formatting complaint:

| Rule | Why |
| :--- | :--- |
| The objective states an **outcome**, not an activity | "Investigate the crash" cannot fail, so it cannot finish. State what will be TRUE. |
| Every goal has `stop_when` | Without it the run grinds past done. Work past the stop line is a defect, not diligence. |
| Every goal has at least one criterion | A goal with no criterion measures nothing. |
| Each criterion has a **binary** `pass_condition` | "works correctly" is rejected. "exit code 0", "returns 200", "grep is empty" pass. |
| Each criterion names its `scenario` | The literal command, request, or action that proves it — decided now, not improvised later. |
| Each criterion names its `expected_evidence` | Written at registration time. Criteria invented after the work bend the contract to fit whatever happened. |

Where the user was silent on a bound the work forks on, set it yourself and record it
in `constraints` as `assumed: <bound> — <rationale>, <reversible?>`. Unstated bounds
do not exist, which is exactly why you write them down.

Ask the user only when the missing detail is genuinely theirs to decide — an
irreversible or destructive choice, a public surface, a real budget. Everything else
gets a stated assumption and proceeds.

## 2. Work a goal, then checkpoint it

Mark a goal started, so a resumed session knows where you were:

```bash
python .agents/scripts/loop.py checkpoint --goal-id g1 --status in_progress --json
```

Then, once you have actually run the scenario:

```bash
python .agents/scripts/loop.py checkpoint --goal-id g1 --status complete \
  --evidence "grep returned nothing; :feature:home compiled clean" \
  --command "./gradlew :feature:home:compileDebugKotlin" --exit-code 0 \
  --evidence-path "build/reports/compile.txt" --json
```

`--evidence` is **required** for any status other than `in_progress`. A status with
no evidence is an assertion, and the loop does not record assertions.

Record what you observed, not what you expect. `--command` and `--exit-code` are what
make a checkpoint auditable later: a hook can validate a recorded exit code without
re-running a 90-second Gradle build, which is the whole reason the evidence lives here.

Use `--status failed` when the scenario ran and did not pass, and `inconclusive` when
you could not run it at all. Both are useful; a silent gap is not.

## 3. Steer when the plan changes — on the record

```bash
# scope grew
python .agents/scripts/loop.py steer --kind add-goal --goals-json new.json \
  --rationale "user asked for the settings screen too" --json

# scope shrank
python .agents/scripts/loop.py steer --kind drop-goal --goal-id g3 \
  --rationale "descoped by the user" --json

# a bound tightened
python .agents/scripts/loop.py steer --kind revise --goal-id g1 \
  --patch-json '{"stop_when": "grep empty and tests green"}' \
  --rationale "tests were part of the ask" --json

# something worth knowing, no goal change
python .agents/scripts/loop.py steer --kind note \
  --rationale "compileDebugKotlin is flaky on this module; using assembleDebug" --json
```

`--rationale` is required. A steer without a reason is unreviewable, and future-you
reading the ledger after compaction is the reviewer.

## 4. Verify the ledger is sufficient

```bash
python .agents/scripts/loop.py reconstruct --check --json
```

Exits non-zero if `goals.json` disagrees with the ledger. Run it before you report
completion: it is the proof that the session's whole history survives losing the cache.

## Stop rules

- **All goals complete** (`all_complete: true` in `status`) → deliver and stop. Do not
  look for more work.
- **A goal's `stop_when` holds** → that goal is done, even if you can see further
  improvements. Note them; do not do them.
- **Three consecutive failed checkpoints on one goal** → stop editing, checkpoint it
  `failed` with what you tried, and surface it. Do not keep grinding.
- **You cannot run a criterion's scenario at all** → checkpoint `inconclusive` and say
  why. Never mark complete on a scenario you did not execute.

A green build is supporting evidence, never completion proof on its own. Audit every
criterion against the evidence actually recorded in this run before reporting done.

## If you are resumed after trying to stop

A `Stop` hook (`.agents/hooks/stop_verifier.py`) holds the session open while a
registered loop still has work, and injects a system message naming the active goal.
It is not a bug and it is not arbitrary — it fires only for a loop **you** registered.

Two things it checks that are worth knowing about:

- **A goal marked `complete` on top of a recorded non-zero exit code is rejected**, as
  is a `--evidence-path` naming a file that does not exist. Record what actually
  happened; a checkpoint that overstates the outcome will simply come back.
- **The ledger must advance.** If a resume produces no new ledger entry, the loop is
  marked stuck and stops for good. Checkpointing `in_progress` as you go is enough.

The way out is never to argue with it: finish the goal, or close it out honestly with
`--status failed` / `--status inconclusive`. Either ends the goal on the record. Resumes
are capped (2 per goal, 1 after a compaction, 6 per session), so nothing spins forever.
