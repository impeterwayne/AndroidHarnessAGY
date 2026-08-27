---
name: ultrawork
description: >
  Maximum-rigour mode for a request that must not come back wrong: classify the intent before
  acting, register the run as goals with evidence, delegate discovery and judgement instead of
  doing everything in one context, and prove the result with commands and exit codes.
  Activates on "ultrawork", "ultra work", "ulw", or when the user asks for maximum rigour,
  "do this properly", "no shortcuts", "be thorough and verify". Use for multi-file features,
  refactors, migrations, hard bugs, and anything where a plausible-looking wrong answer is
  expensive. Do NOT use it for a one-line change — the overhead would be the whole cost.
metadata:
  short-description: Rigour mode — classify, register goals, delegate, prove
---

# ultrawork

Open your reply with `ultrawork:` and one line naming what you are about to do. That line is
the activation receipt — without it, nobody can tell this mode engaged.

This mode changes **how carefully** you work. It does not change **how much** you build:
[`lean`](../lean/SKILL.md) remains the sole authority on that, and its YAGNI ladder
still governs every line. Rigour and minimalism are not in tension — the failure being
prevented here is confident wrongness, not small code.

## 1. Classify the intent, before any tool call

State the classification in one line: **research | investigation | evaluation | fix |
implementation**.

| The user said | It is not a request to change code |
| :--- | :--- |
| "explain how X works", "how does Y do Z" | research → explain → stop |
| "look into this", "check whether", "why is" | investigation → report → stop |
| "what do you think of", "would X be better" | evaluation → recommend → stop |
| "this crashes", "this is broken" | fix → the smallest correct fix, not a refactor |

The failure mode this exists to stop is reading a request and starting to code. Only an
explicit ask to build, add, change, or implement authorises edits. When a request genuinely
carries two intents ("explain this and fix it"), name both and do them in that order.

## 2. Register the run before the first edit

Implementation and fix work goes through the [`loop`](../loop/SKILL.md) skill:

```bash
python .agents/scripts/loop.py create-goals --brief "<the request, verbatim>" \
  --goals-json goals.json --json
```

This is not bookkeeping. It is the run's contract, and three things depend on it:

- The goal quality bar is **enforced** — activity-only objectives, unfalsifiable pass
  conditions and criteria without `expected_evidence` are rejected at registration. Writing
  goals that pass is most of the thinking.
- The ledger is your durable memory. After a compaction, `loop.py status --json` is the first
  thing you run, and you resume from what it reports instead of re-planning.
- The `Stop` gate (`.agents/hooks/stop_verifier.py`) holds the session open until those goals
  hold, and rejects a `complete` checkpoint sitting on a non-zero recorded exit code.

Every criterion names its scenario — the literal command — and its expected evidence, decided
**now**, before any code exists. Criteria invented afterwards bend to fit whatever happened.

Where the user was silent on a bound the work forks on, choose it, record it in `constraints`
as `assumed: <bound> — <rationale>, <reversible?>`, and proceed. Ask only when the missing
detail is genuinely theirs: an irreversible choice, a public surface, a real budget.

## 3. Delegate discovery and judgement

You have a context window and it is the scarcest thing in the run. Spend it on decisions, not
on file contents you could have had summarised.

| Need | Call |
| :--- | :--- |
| Where is X, which files touch Y | `explore` — fan out 2–3 in **one** `invoke_subagent` call |
| Architecture trade-off, review of finished work, a bug that survived two fix attempts | `oracle` (read-only, no shell) |
| One mechanical single-file edit | `worker-quick` (no shell) |
| A feature, a refactor, anything needing a build to prove it | `worker-deep` |

```
invoke_subagent(Subagents=[
  {TypeName: "explore", Workspace: "inherit", Model: "inherit", Prompt: "..."},
  {TypeName: "explore", Workspace: "inherit", Model: "inherit", Prompt: "..."}
])
```

`Subagents` is an array — N independent questions are one call, not N calls in sequence. Give a
worker the goal, the constraints and the file paths; never a numbered plan for it to follow.
Then verify its result yourself with `view_file`: a subagent's summary of what it did is not
evidence that it did it.

Do it yourself when the task is one obvious edit, or when you already hold all the context.
Delegating a one-liner costs more than doing it.

## 4. Prove it — evidence, not assertion

Nothing is done without a command that would have caught the mistake, and its exit code:

- Compile the affected module: `./gradlew :<module>:compileDebugKotlin`
- Run the tests covering what you touched: `./gradlew :<module>:testDebugUnitTest`
- For a UI change, exercise the real surface — the [`scrcpy`](../scrcpy/SKILL.md) skill drives
  the device and captures screenshots. A compile is not proof that a screen renders.
- Record each one: `loop.py checkpoint --goal-id gN --status complete --evidence "..."
  --command "..." --exit-code 0`

Where a test seam exists, write the failing test first and read its failure message — confirm
it fails for the *right* reason, not on an import or a typo — then make it pass. A test written
after the code passes tells you nothing about whether it can fail.

Pre-existing failures are not yours to fix: establish that they failed before your change, then
say so explicitly.

**Never** suppress a type error, delete or skip a failing test to go green, or commit unless the
user asked for a commit.

## 5. Before you claim done

Answer these honestly. Any "no" is unfinished work, not a caveat to mention in the report:

1. Does every criterion I registered have evidence recorded in **this** run?
2. Did I read the actual output of every command, or skim it?
3. Did the module compile, and did the tests I claim pass actually run?
4. Is every part of the request implemented — re-read the original request now?
5. Did I classify the intent at the start, and does what I did match that classification?
6. Is anything a stub, a `TODO`, or a "you can extend this later"?

Then run `loop.py reconstruct --check --json`: it proves the record survives losing its cache,
which is the only durable claim you can make about the run.

## Completeness, not maximalism

Deliver the **requested scope, finished and verified** — no stubs, no `TODO`, no half-wired
code path. "Proof of concept" is not an acceptable delivery when a working implementation was
asked for.

That is a bar on *finishing*, not a licence to build more. No speculative parameters, no
interfaces with one implementation, no scaffolding for future requirements, no single-class
factories. The shortest idiomatic Kotlin that fully does the job is the target. Complete and
small are not in tension — incomplete and over-built are both failures.

Being asked for rigour is not permission to widen the scope. If you find real problems outside
what was asked, name them at the end; do not fix them.

## Stop rules

- **All registered goals complete, evidence recorded** → report and stop. Do not look for more
  work, and do not keep polishing.
- **A goal's `stop_when` holds** → that goal is done, even if you can see improvements. Note
  them, leave them.
- **Three consecutive failed attempts at the same problem** → stop editing, checkpoint the goal
  `failed` with what each attempt produced and where you believe the real problem is, and
  surface it. A clean stop with a good failure report beats broken code and an optimistic
  summary.
- **A criterion you cannot run at all** → checkpoint `inconclusive` and say why. Never mark
  complete on a scenario you did not execute.

Work past the stop line is a defect, not diligence.
