# OMO → Antigravity Port: steps 1–8 done, follow-ups open

Companion to [`MAPPING.md`](MAPPING.md), which holds the decisions and the *why*.
This file is the executable plan for what is left. Written 2026-08-27 to hand off to
a fresh session.

**Read `MAPPING.md` first** — especially "Rejected" (so you don't rebuild something
we deliberately ruled out) and "Probe findings" (platform facts that were established
empirically and should not be re-derived).

---

## Where things stand

All eight steps (including 5b) are done. Two things to read before building on this:

- **`orchestrator.md` is not reachable** — `mainAgent` does not work in CLI 1.1.22, and the
  invariant it carried moved to step 5b. See "Step 5 — verification owed".
- **Workflow files are deprecated** (established in step 8), and `.agents/workflows/` is now
  gone: skills are what serve slash commands. See "Workflow → skill migration" below, which
  also records the two live probes that finally closed step 5's acceptance test.

| Path | What it is |
| :--- | :--- |
| `.agents/hooks.json` | 6 profiles: `kotlin-rule-gate` (on), `scrcpy-daemon` (on), `ultrawork-intent-gate` (on), `stop-verifier` (on), `root-write-guard` (off), `omo-port-probe` (off) |
| `.agents/hooks/rule_gate.py` | `PreToolUse` gate: Kotlin comments / hardcoded UI strings / raw hex. `--self-test`, `--scan <path>` |
| `.agents/hooks/scrcpy_daemon.py` | Owns the scrcpy daemon. `--self-test`, `--status` |
| `.agents/hooks/probe.py` | Hook-payload probe, disabled. Re-enable to answer new payload questions |
| `.agents/agents/*.md` | 7 agents, flat files. `call_mcp_tool` removed from `tools:` (it broke construction) |
| `.agents/agents/{orchestrator,explore,oracle,executor}.md` | Step 5. Bodies 83–124 lines, adapted from OMO. `executor` merged `worker-quick`+`worker-deep` on 2026-08-28 (MAPPING: "Tiers collapsed to one `executor`") |
| `.agents/skills/code-review/SKILL.md` | Delegating review. Was `workflows/code-review.md` until workflows turned out to be deprecated; **live-verified** to resolve as `/code-review` and to fan out three `explore` subagents plus an `oracle` consult |
| `.agents/scripts/loop.py` | Step 6. Goal loop CLI: `create-goals`, `status`, `checkpoint`, `steer`, `reconstruct`, `--self-test` (35 fixtures). **Fails loud**, unlike the hooks |
| `.agents/skills/loop/SKILL.md` | Teaches the model the loop CLI's grammar and its stop rules |
| `.agents/hooks/write_guard.py` | Step 5b. `PreToolUse` root-session write gate. `--self-test`, `--status`, `--off`/`--on`. Profile **off by default** |
| `.agents/hooks/stop_verifier.py` | Step 7. `Stop` gate: holds an owned goal loop open until its goals hold. `--self-test` (52 fixtures), `--status`, `--off`/`--on`, `--clear`. Profile **on** |
| `.agents/hooks/intent_gate.py` | Step 8. `PreInvocation` gate: the word "ultrawork" in a prompt → an injected directive. `--self-test` (38 fixtures), `--status`, `--scan`, `--print-directive`, `--off`/`--on`. Profile **on** |
| `.agents/skills/ultrawork/SKILL.md` | Step 8. Rigour mode: classify intent, register goals, delegate, prove. A **skill**, because workflows are deprecated — so `/ultrawork` works natively |
| `docs/omo-port/MAPPING.md` | Decision ledger, probe findings, open questions |

---

## Platform facts already established — do not re-derive

All verified on this machine, Antigravity CLI 1.1.22, `gemini-3.7-flash-high`.

**Hooks**
- Hook CWD is `.agents/` (the directory containing `hooks.json`). Use `python hooks/x.py`.
- `PreInvocation`, `PostInvocation`, `Stop` all fire **inside subagents**, each with its own
  `conversationId`, brain dir and transcript.
- `PreInvocation` fires ~50×/session and carries **no prompt text**. `Pre`/`Post` are not
  paired (53 vs 51 observed) — don't build a state machine that assumes pairing.
- `PreToolUse` has `toolCall.args`; **`PostToolUse` does not** (per docs — not empirically
  checked), so a post-hoc hook cannot know which file was touched.
- `PostToolUse` output schema is `{}` only: you can rewrite tool *args* via
  `PreToolUse.overwrite`, never tool *results*.
- `Stop` payload adds `error`, `executionNum`, `fullyIdle`, `terminationReason`.
- `terminationReason` values are the runtime's `TERMINATION_REASON_*` enum **minus the
  prefix** — the docs' `model_stop` / `max_steps_exceeded` do not exist. Observed:
  `NO_TOOL_CALL` (a normal model stop). Full vocabulary, read out of `agy.exe`:
  `UNSPECIFIED, NO_TOOL_CALL, ERROR, HALTED_STEP, EARLY_CONTINUE, INJECTED_RESPONSE,
  MAX_INVOCATIONS, MAX_FORCED_INVOCATIONS, MAX_TOKEN_BUDGET_EXCEEDED, USER_CANCELED,
  TERMINAL_STEP_TYPE, TERMINAL_CUSTOM_HOOK`. Normalise before comparing.
- `executionNum` was **0** on all four observed Stops — it is not a usable turn counter.
- `{"decision": "stop"}` is the proven-safe permit value (4 real Stops via `probe.py`).
  A `continue` verdict lands in the agent's transcript as a `SYSTEM_MESSAGE`/`SYSTEM`
  record prefixed `Stop hook blocked termination: `.
- The runtime caps stop-hook continuations itself
  (`CascadeExecutorConfig.max_stop_hook_continuations`; changelog: "after a configurable
  number of consecutive continuations, the hook can no longer block"). The value is not
  readable from here — treat it as a backstop, never as your brake.
- **Compaction is detectable from the transcript.** The runtime injects, verbatim:
  `**The earlier parts of this conversation have been truncated due to its long length.
  The following content summarizes the truncated context so that you may continue your
  work. **`
- **`$ANTIGRAVITY_CONVERSATION_ID` is set in `run_command`'s environment** and equals the
  hook payload's `conversationId` (live-verified). `AGY_CONVERSATION_ID` does not exist.
- **Design rule:** `PreToolUse` only when the hook's job is to *gate* — it forces a
  `decision` on every matched call. Everything else goes on `PreInvocation`/`Stop`.

**Transcripts** — `~/.gemini/antigravity-cli/brain/<conversationId>/.system_generated/logs/transcript_full.jsonl`
(note: `transcript_full`, not `transcript` as the docs claim). Records are **snake_case**
(hook payloads are camelCase): `{type, source, content, created_at, status, step_index}`,
plus `tool_calls` and `thinking`.
`type ∈ {USER_INPUT, PLANNER_RESPONSE, GENERIC, SYSTEM_MESSAGE, EPHEMERAL_MESSAGE}`,
`source ∈ {USER_EXPLICIT, MODEL, SYSTEM, SYSTEM_SDK}`. User prompts are
`USER_INPUT`/`USER_EXPLICIT` wrapped in `<USER_REQUEST>` + `<ADDITIONAL_METADATA>`, sometimes
`<SKILL>`. A hook's `injectSteps[].ephemeralMessage` lands as
`EPHEMERAL_MESSAGE`/`SYSTEM_SDK`; a `Stop` continuation lands as `SYSTEM_MESSAGE`/`SYSTEM`.
Neither is ever a `USER_INPUT`, so a content-injecting hook cannot re-trigger itself through
the user-record path — but its marker text *does* reappear in `GENERIC`/`MODEL` tool results
when an agent reads the hook's own source or config.

**Skills, workflows and slash commands**
- **Workflows are deprecated.** `.agents/workflows/*.md` is legacy; the runtime ships a
  built-in `migrate-workflows` skill that says so and migrates them to
  `.agents/skills/<name>/SKILL.md`.
- **Skills are the slash-command mechanism.** `/<name>` resolves to a *skill*, and arrives in
  the transcript as `<SKILL>The user has explicitly invoked the (<name>) skill…` inside the
  user record's `<ADDITIONAL_METADATA>` block — with the skill's **entire body inlined**. Any
  hook matching on prompt content must therefore scope its match to `<USER_REQUEST>`.
- Skills also get semantic discovery: the agent may invoke one on its own when the
  `description` fits. Write descriptions as activation conditions, not summaries.
- When a skill and a workflow shared a name (`figma-to-compose` did), the **skill** is what
  the slash command served. That was the evidence that settled the deprecation question.

**Agents**
- Flat files: `.agents/agents/<name>.md`, filename matching frontmatter `name:`.
- Dispatch: `invoke_subagent` with
  `{"Subagents":[{"Model","Workspace","TypeName","Role","Prompt"}], "toolAction", "toolSummary"}`.
  `TypeName` = frontmatter `name:`. `Subagents` is an **array** — N spawns per call.
- `tools:` is **not** the runtime tool set. The runtime always adds `send_message`,
  `schedule`, `call_mcp_tool`, `list_resources`, `read_resource`, `manage_task` — but **not**
  `invoke_subagent` or `run_command`. So MCP access is automatic, and **listing
  `call_mcp_tool` in `tools:` makes the agent fail to construct**.
- `tools:` **is enforced for subagents** (hard-verified: `oracle` had no shell and no write
  tools) but `mainAgent` selection via `agy --agent <name>` does not load the agent at all in
  CLI 1.1.22, so "the orchestrator cannot write" holds **only on the subagent path**.
- Any agent holding `run_command` can write through the shell regardless of its file tools.
- A subagent that fails to construct leaves an **empty brain dir and no hook records**.
- `model:` accepts **only `inherit` / `flash`**. A real model id such as
  `gemini-3.7-flash-high` is valid for `--model` and `agy models` but makes the agent fail to
  construct — and it is *not* logged to `cli.log`, so the only symptom is
  `not found or not allowed to be invoked` at dispatch. Use `inherit`; the session model is
  already `gemini-3.7-flash-high`.
- Every construction failure looks the same from outside. Change one variable at a time.

**Subagent vs main-session detection** — the child payload has no parent pointer. Solved in
`write_guard.py`; reuse it rather than rewriting it.

⚠️ The relationship is recorded from **both** ends, so "another transcript mentions my id"
is *not* a discriminator — it reports every parent as a child:

| Direction | Record |
| :--- | :--- |
| parent, on spawn | `Created the following subagents:\n{ "conversationId":  "<child>"` |
| child, on report | `Message sent to "<parent>".` + a `send_message` tool call |

The working test needs my `conversationId` **and** the literal
`Created the following subagents` in the *same* record. Measured ~15ms cold over 505 brain
dirs (newest-first, capped at 60), 0.11ms cached — fine for `PreToolUse` on write tools and
for `Stop`, still too slow for every `PreInvocation`.

Cache `delegate` only. `root` is inferred from absence, which is indistinguishable from a
parent that has not flushed yet, so caching it makes an early misread permanent.

Where it applies, still prefer not detecting at all: key off transcript *content* instead (a
subagent's task prompt won't contain your trigger word unless the orchestrator put it there).

---

## Conventions to follow

- **Hook handlers**: Python (cross-platform; the repo already ships Python in skills). Always
  print valid JSON on stdout, diagnostics to stderr, and **fail open** — a gate that blocks
  work because of its own bug is worse than one that misses a violation.
- **Self-verifying scripts**: every handler gets `--self-test` (fixtures) and, where a corpus
  exists, `--scan`. `rule_gate.py` is the reference shape.
- **State**: `.agents/state/…`, gitignored. Keyed by `conversationId`. Never assume it exists.
- **Test corpus**: `CodebaseCompose/` → symlink to the real `com.genesys` app, 90 `*.kt`.
  Any new Kotlin-touching rule must score **0 false positives** across it.
- **Licensing**: OMO is Sustainable Use License. Port *algorithms*, not code. See MAPPING.

---

## Step 5 — verification owed

The five files are written (2026-08-27), with sources adapted per the Q5 decision
(internal-only, adapting OMO prose is permitted):

All five use **`model: inherit`** — which resolves to the session model,
`gemini-3.7-flash-high`. Do **not** put a full model id here: it is a valid `--model` value
but makes the agent fail to construct (see MAPPING). Any behaviour difference between tiers
therefore comes from the prompt and tool set, not the model.

| File | `tools:` | Adapted from |
| :--- | :--- | :--- |
| `orchestrator.md` | `view_file`, `grep_search`, `list_dir`, `invoke_subagent` | `sisyphus-dynamic-prompt-{role,execution}.ts` |
| `explore.md` | + `run_command`, no write tools | `agents/explore.ts` |
| `oracle.md` | read-only, no shell | `agents/oracle.ts` (default variant) |
| `worker-quick.md` | write tools, **no shell** | `QUICK_CATEGORY_PROMPT_APPEND` |
| `worker-deep.md` | write tools + `run_command` | `DEEP_CATEGORY_PROMPT_APPEND_GPT_5_5` |

The two worker rows are the 2026-08-27 state. They were merged into `executor.md` (write
tools + `run_command`, both prompt sources) on 2026-08-28 — the provenance is recorded here
because it is what the license note in MAPPING refers to.

Checked locally: YAML parses for all five, each filename matches its `name:`, bodies are
51–102 lines (under the 120 cap).

**Verified 2026-08-27** in a live interactive session driven through herdr:

- `worker-quick` and `figma-analyzer` (plus two throwaway layout probes) all construct and
  run when dispatched as `invoke_subagent(TypeName=…, Workspace="inherit", Model="inherit")`.
- The flat `.agents/agents/<name>.md` layout is fine — tested head-to-head against
  `<name>/agent.md`; both work.
- A detour worth not repeating: pinning `model: gemini-3.7-flash-high` broke **every** agent,
  including previously-working ones. See MAPPING. `inherit` is the value.

- **`tools:` is enforced on subagents.** `oracle` reported `NO_RUN_COMMAND_TOOL` and a tool
  list exactly matching its frontmatter plus the base set — read from its own transcript,
  not a relay. The read-only guarantee is real on this path.
- **`mainAgent: true` does NOT work via `agy --agent <name>`.** Three probes agree: the
  orchestrator body never reaches the system prompt, and the session runs the default agent
  with a full toolset (it ran `git status` despite declaring no shell).

**The blocker this creates.** Step 5's premise — "the orchestrator never writes code" — has
no main-agent path in CLI 1.1.22. `orchestrator.md` is currently unreachable. Pick one
before step 6:

1. Add `subagent: true` to `orchestrator` and dispatch it from an ordinary session. `tools:`
   binds, but it stops being the session driver, so the human talks to a default agent that
   delegates to the orchestrator that delegates again — two hops, and the intent gate lands
   in the wrong place.
2. **Move the process into the workflow file** (`code-review.md` already holds it) and keep
   only the tier subagents as agents. This is what demonstrably works today, needs no new
   mechanism, and loses only the persona.
3. Retest on the Antigravity 2.0 desktop app, where custom agents are chosen from a
   dropdown — `mainAgent` may work there and be CLI-only broken.

**Still open:**

1. **Does `orchestrator` construct?** Untested — it is the one agent never dispatched,
   because it is `mainAgent`-only. Its `invoke_subagent` declaration is still unproven (Q10).
   Adding `subagent: true` would let you test it in one prompt.
2. **Does `/code-review` actually delegate?** The workflow names all five agents and fans
   out three parallel `explore` calls in Phase 1.

*How to drive a live test:* `herdr tab create --cwd <repo> --label t --no-focus`, then
`herdr agent start t --kind agy --pane <id>`, then `herdr agent prompt t '<prompt>' --wait`.
Agent discovery happens at session start, so **restart the session after editing an agent
file**.

*Acceptance (unchanged)*: `/code-review` runs end-to-end through `orchestrator` and the
orchestrator writes no code itself. A bad `tools:` entry fails silently apart from an
error string in the parent's transcript, so check construction explicitly.

**Deliberately not set:** `commandExecutionPolicy: auto` / `permissionMode: acceptEdits`
on the executor. They are real frontmatter keys (doc 01) and would suit its
autonomous Gradle runs, but they loosen permissions — opt in knowingly, not by default.

---

## Step 5b — Root write guard ✅ done 2026-08-27

`.agents/hooks/write_guard.py`, profile `root-write-guard`, **`enabled: false`**.

Denies writes to *source* files (`.kt .kts .java .xml .gradle .pro .py .sh .ps1 .json
.toml .properties`, plus `*.gradle.kts`) when the caller is the root session; passes them
for delegates. Docs, notes and plans are never gated — the invariant is "never writes
code", and a root session that cannot write a plan cannot do its job.

*Acceptance met*: a delegate writes while its parent cannot. 31 fixtures plus 3 real
conversation ids. ~15ms cold across 505 brain dirs, 0.11ms cached.

```
python hooks/write_guard.py --status     # is the gate armed, what is cached
python hooks/write_guard.py --off / --on # escape hatch, no config edit needed
python hooks/write_guard.py --self-test
```

**Read this before touching the detection.** The parent/child relationship is recorded
from *both* ends:

| Direction | Record |
| :--- | :--- |
| parent, on spawn | `Created the following subagents:\n{ "conversationId":  "<child>"` |
| child, on report | `Message sent to "<parent>".` + a `send_message` tool call |

So "does another transcript mention my id" reports **every parent as a delegate**. This
was caught only by running the classifier against two real ids — the fixtures passed
happily with the wrong logic. The working test needs the id and the literal
`Created the following subagents` in the *same* record.

Also deliberate: only `delegate` is cached. `root` is inferred from absence, which is
indistinguishable from a parent that has not flushed its transcript yet, so caching it
would make an early misread permanent for the session.

**Unverified, and it matters:** how Antigravity combines two `PreToolUse` verdicts when
this and `kotlin-rule-gate` both match the same write. Most-restrictive, first, or last
all seem plausible. Settle it before enabling this in anger.

---

## Step 6 — Loop state + CLI ✅ done 2026-08-27

`.agents/scripts/loop.py` + `.agents/skills/loop/SKILL.md`. State at
`.agents/state/loop/<session>/`: append-only `ledger.jsonl` (authoritative) and `goals.json`
(derived cache, written atomically).

| Subcommand | Does |
| :--- | :--- |
| `create-goals --brief … --goals-json …` | registers the goal set; refuses to overwrite an existing one without `--force` |
| `status [--json]` | progress, active goal, last ledger event — the after-compaction entry point |
| `checkpoint --goal-id --status --evidence [--command --exit-code --evidence-path]` | records an outcome; `--evidence` required for anything but `in_progress` |
| `steer --kind add-goal\|drop-goal\|revise\|note --rationale …` | changes the goal set on the record |
| `reconstruct [--check]` | rebuilds the cache from the ledger; `--check` proves they agree |
| `--self-test` | 35 fixtures |

*Acceptance met*: `reconstruct --check` fails on cache drift, and deleting `goals.json`
entirely loses nothing — both asserted in the suite.

Notes for whoever builds step 7 on top of this:

- **The CLI fails loud** (non-zero exit, reason on stderr) — the opposite of the hooks'
  fail-open rule, and deliberately so. A hook that blocks work on its own bug is worse than
  one that misses a violation; a CLI that half-records progress lets the agent believe
  evidence exists when it does not.
- The goal quality bar from OMO's `define-goal.md` is enforced **mechanically**, not advised:
  activity-only objectives, unfalsifiable pass conditions, missing `stop_when`, and criteria
  lacking `expected_evidence` are rejected at registration.
- `checkpoint` stores `command` + `exit_code` + `evidence_paths` precisely so step 7 can
  validate a *recorded* exit code instead of re-running a 90s Gradle build inside a hook.
- **Session id is the loose joint.** It resolves `--session` → `$AGY_CONVERSATION_ID` →
  `$ANTIGRAVITY_CONVERSATION_ID` → `default`. Whether Antigravity sets either env var is
  unverified. Step 7's hook *does* receive `conversationId`, so either confirm the env var
  or add a reconciliation step; do not assume the directory name matches.
- `ledger_seq` is dense and monotonic — that is the "did the ledger advance" signal step 7
  needs for stuck detection. Don't use turn count.

---

## Step 7 — `stop_verifier.py` ✅ done 2026-08-27

`.agents/hooks/stop_verifier.py`, profile `stop-verifier`, **`enabled: true`** — it is inert
unless the stopping conversation *owns* a loop under `.agents/state/loop/`, which is what
both scopes it to the main session and keeps it from fighting subagents (a delegate does not
own its parent's loop).

Brakes, in order. Every one of them exits by **permitting** the stop:

| # | Condition | Verdict |
| :--- | :--- | :--- |
| 1 | off switch present | permit |
| 2 | no loop owned by this conversation | permit |
| 3 | `terminationReason ∈ {EARLY_CONTINUE, INJECTED_RESPONSE}` — not a real stop | permit, counters untouched |
| 4 | hard stop: non-empty `error`, or reason outside `{NO_TOOL_CALL, TERMINAL_STEP_TYPE, UNSPECIFIED, ""}` | permit |
| 5 | `fullyIdle: false` — steps or children in flight | permit, counters untouched |
| 6 | loop already marked stuck | permit |
| 7 | inside a failure cooldown (30s, doubling) | permit |
| 8 | no goals; or all complete and the record holds | permit ← the good exit |
| 9 | 3 consecutive failed checkpoints (the SKILL's own rule) | permit |
| 10 | **ledger did not advance** since the last resume | mark stuck, permit |
| 11 | resume budget spent — 2/goal (1 after compaction), 6/session | permit |
| else | | `continue`, with the goal, its criteria and the exact checkpoint command |

Verification validates the **record**: a recorded non-zero `exit_code` under a `complete`
goal, a missing `evidence_path` artifact, or `goals.json` drifting from the ledger each block
the stop. No build is ever run inside the hook.

```
python hooks/stop_verifier.py --status              # loops seen, resumes spent, stuck flags
python hooks/stop_verifier.py --off / --on          # escape hatch, no config edit
python hooks/stop_verifier.py --clear [--session X] # reset budgets and stuck flags
python hooks/stop_verifier.py --self-test           # 52 fixtures
```

*Acceptance met.* 52 fixtures, including "a productive-but-unfinished loop resumes at most
twice, then permits for good" and "a resume that produced no ledger entry is stuck, not
resumed again". Cost: ~51ms per Stop with no loop registered (Python startup), ~70ms worst
case with a 6MB transcript.

**Verified live** (CLI 1.1.22, driven through herdr, two-goal loop):

- Told to answer and stop with an unfinished goal, the agent was resumed **once**, did the
  work, checkpointed with `--command`/`--exit-code`, and the next Stop permitted. No churn.
- Given a deliberately unsatisfiable goal, it resumed once, ran the scenario, and checkpointed
  `failed` with the exit code — closing the loop out on the record. **The designed exit is
  cheaper than the resume cap**, which is the outcome to aim for in step 8's prompts too.
- The block reaches the agent as a `SYSTEM_MESSAGE`/`SYSTEM` transcript record, prefixed by
  the runtime with `Stop hook blocked termination: `. Write `reason` as a standalone
  instruction, not as a sentence continuation.

**Deliberate divergence from the original plan.** The plan said to *suppress* on context
pressure. But the loop exists precisely to survive compaction — the skill's first instruction
after context loss is `loop.py status --json` — so suppressing would discard the mechanism at
the moment it earns its keep. Instead compaction tightens the per-goal budget to **one**
resume and the injected reason leads with "read your own status first". An amnesiac that then
does nothing is caught by the ledger-advance check (10) on the next Stop.

**Two things step 6 left open are now closed:**

- `$ANTIGRAVITY_CONVERSATION_ID` **is** injected into `run_command`'s environment, and it
  equals the hook payload's `conversationId` (both live-verified; the brain dir with that name
  exists). So loop.py's directory name *is* the conversation, and `--session` is only needed
  for deliberately separate work. `AGY_CONVERSATION_ID` does not exist — that first candidate
  in loop.py's chain never fires.
- The transcript-adoption fallback is still implemented (it looks for `loop.py` in the
  conversation's own transcript, honours a `--session` it finds there, else adopts `default`
  and writes a claim file so a second conversation cannot steal it). It is the safety net, not
  the plan.

---

## Step 8 — Intent gate + ultrawork ✅ done 2026-08-27

Two files, plus one finding that changed the shape of the deliverable.

### `.agents/skills/ultrawork/SKILL.md` — **a skill, not a workflow**

The plan said `.agents/workflows/ultrawork.md`. Don't: **workflows are deprecated.** The
runtime ships a built-in `migrate-workflows` skill whose own text says so —
"Workflows (`.agents/workflows/*.md` or `_agents/workflows/*.md`) are deprecated. Skills
(`.agents/skills/<name>/SKILL.md`) provide all the capabilities of workflows, plus
first-class slash command support (typing `/<name>`), semantic agent discovery, and
multi-file capabilities." Confirmed from the other end in a real transcript: typing
`/figma-to-compose` produced `<SKILL>The user has explicitly invoked the
(figma-to-compose) skill`, served from `.agents/skills/figma-to-compose/`, not from the
same-named workflow file. **Skills *are* the slash-command mechanism.**

So ultrawork is a skill, and it gets `/ultrawork` plus semantic discovery for free.
Rewritten from OMO's `ultrawork/gemini.md` (325 lines → 130), mapped onto what this harness
actually has: `invoke_subagent` fan-out instead of `task()`, `explore`/`oracle`/`executor`
instead of OMO's roster, Gradle compile + `testDebugUnitTest` instead of `lsp_diagnostics`,
the `scrcpy` skill for real-surface QA, and — the useful substitution — **`loop.py`
create-goals in place of OMO's "GOAL REGISTRATION" *and* its `mktemp` durable notepad.** The
loop already enforces the goal quality bar and step 7 already enforces the goals, so the
skill points at them instead of restating them.

Q6 applied as decided (completeness, not maximalism). Also dropped: OMO's mandatory commit
discipline, which contradicts this repo's "never commit unless asked".

### `.agents/hooks/intent_gate.py` — profile `ultrawork-intent-gate`, **enabled**

`PreInvocation` → `{"injectSteps":[{"ephemeralMessage": "<ultrawork-mode>…"}]}` when the
literal word `ultrawork` / `ultra work` / `ulw` appears in a user prompt.

It fires ~50×/session, so the design is all about cost and precision:

- **Incremental scan.** Transcripts are append-only, so the hook stores a byte offset per
  `conversationId` and reads only what was appended. Steady state is a `stat` plus a
  256-byte head check (file identity — size alone cannot detect rotation): **50ms, i.e.
  pure Python startup.** First invocation of a conversation reads the whole file: 65ms over
  a 1MB transcript.
- **Once per prompt.** A trigger only counts in the newest scanned region, and records are
  fingerprinted (`created_at` + request text). Capped at 8 activations per conversation.
- **Match only inside `<USER_REQUEST>`.** The `<ADDITIONAL_METADATA>` block that follows it
  inlines the *entire body* of any skill invoked by slash command — matching the raw record
  would fire on any skill that merely mentions the word.
- **Stand down when the platform already did it.** `invoked the (ultrawork) skill` in the
  same record means `/ultrawork` loaded it natively; injecting again is pure waste.
- **Cannot feed itself.** Every injection carries `<ultrawork-mode>`, and records containing
  it are skipped.

Keying on a literal word scopes it to the main session for free. Fuzzy activation ("do this
properly") is left to the skill's `description` and Antigravity's semantic discovery — a
regex for intent would fire on prose *about* rigour.

*Verified*: 38 fixtures (36 at first write, plus 2 for a bug the delegated review found — see
"Workflow → skill migration"), plus live (CLI 1.1.22). Prompted `ultrawork this: explain how the
scrcpy daemon hook decides…`, the agent was injected once, read
`.agents/skills/ultrawork/SKILL.md` with `view_file`, opened its reply with `ultrawork:`,
classified the request **research**, and changed nothing. Gate state: `armed: 1`.

**New transcript facts from that run** — the injection lands as
`type: EPHEMERAL_MESSAGE`, `source: SYSTEM_SDK`, two vocabulary values not previously
recorded. It is never a `USER_INPUT`, so the self-feed hazard the plan warned about is
structurally absent; the marker check is belt-and-braces. (The marker *does* show up in
`GENERIC`/`MODEL` tool-result records, e.g. when an agent reads `hooks.json` — another
reason to filter on record type rather than on content alone.)

```
python hooks/intent_gate.py --status            # per-conversation offsets and activations
python hooks/intent_gate.py --print-directive   # exactly what gets injected
python hooks/intent_gate.py --scan <transcript> # would this fire, and if not, why not
python hooks/intent_gate.py --off / --on
python hooks/intent_gate.py --self-test         # 38 fixtures
```

⚠️ This is the **second** `PreInvocation` handler (alongside `scrcpy-daemon`), so every LLM
call now pays two Python startups, ~100ms total. If a third ever appears, merge them into
one dispatcher rather than adding another 50ms.

---

## Verification recipe (herdr)

The whole loop above is testable without leaving the session. Find the live Antigravity agent:

```bash
herdr agent list        # look for "agent":"agy" with agent_status idle; name is pane-derived
```

Then drive it (name will differ per session):

```bash
herdr agent prompt <name> '<prompt>' --wait --timeout 240000
herdr agent read <name> | tail -40
```

Notes learned the hard way:
- **Identity-probe before anything else.** `--agent <name>` fails silently, so a session
  that looks like your custom agent may be the default one. Ask it to quote a heading from
  its own body; a wrong answer voids every other observation from that session.
- **Never ask an agent to list its tools** — it will produce a plausible list either way.
  Ask it to *use* the tool and report the literal output.
- `grep "not found in registry" ~/.gemini/antigravity-cli/cli.log` is the loud signal for a
  bad `tools:` entry. It records the offending tool name verbatim.
- `agy models`, `agy agent`, and `strings agy.exe` answer some questions with no session at
  all — try those first. See MAPPING, "CLI introspection findings".
- Non-interactive `--print` did **not** discover workspace agents here. Use a real
  interactive session in the workspace.
- A CLI survey/dialog can swallow a submission — if `prompt` returns without `result`, check
  `herdr agent read` and re-send.
- Verify independently of the agent's self-report by parsing the brain-dir transcript; the
  agent's summary of what it did is not evidence.
- Re-enable the `omo-port-probe` profile in `hooks.json` when you need raw hook payloads.

---

## Open questions

Carried from MAPPING; none block step 5.

| # | Question | Blocks |
| :--- | :--- | :--- |
| 2 | Is there a per-agent `hooks:` frontmatter key? (Blog doc says agents scope "skills, MCP servers, and hooks"; no key documented) | would solve parent/child hook scoping declaratively |
| 4 | Accepted `model:` vocabulary beyond `flash` / `inherit` — and whether they differ | whether the two worker tiers are actually different models |
| 9 | Arg shape of `replace_file_content` / `multi_replace_file_content` | rule-gate precision on edits. `rule_gate.py` already logs unknown shapes to `.agents/state/rule_gate_unknown_args.jsonl` and passes through — check that file after a session with Kotlin edits |
| 10 | Is `invoke_subagent` a valid `tools:` registry name? | **whether `orchestrator` constructs at all.** Test before anything else |
| 11 | Does `mainAgent: true` work at all? | **blocks step 5's premise** — answered NO for CLI 1.1.22; see "verification owed" above |

Q5 and Q6 were **decided 2026-08-27** — internal-only sourcing, and completeness-not-
maximalism for ultrawork. See MAPPING's open-questions table for the full wording.

---

## Workflow → skill migration ✅ done 2026-08-27

`.agents/workflows/` is **gone**. Done by hand rather than with the runtime's
`migrate-workflows` skill, because two of the three files did not want a 1:1 conversion:

| Was | Now | Why |
| :--- | :--- | :--- |
| `workflows/code-review.md` | `.agents/skills/code-review/SKILL.md` | The real migration — there was no skill counterpart. Rewritten to address the **session agent** in the second person instead of "the orchestrator", which is the incoherence step 5 left behind when `mainAgent` turned out not to work |
| `workflows/figma-to-compose.md` | folded into `.agents/skills/figma-to-compose/SKILL.md` | A same-named skill already existed and was strictly richer. Its one unique asset was the *orchestration* — which subagent runs which phase — now an "Upstream pipeline" section ahead of Step 1 |
| `workflows/feature-orbit-mvi.md` | folded into `.agents/skills/orbit-mvi-feature-builder/SKILL.md` | 35 lines against the skill's 227, and superseded except for its domain/data phase, now "Stage 0: Domain and Data Contracts". A second near-duplicate skill would have made semantic discovery worse, not better |

A duplicate skill is worse than a missing one: discovery has to pick between them. Folding
was the right shape twice out of three times.

**Lost in the move:** the `/feature-mvi` shorthand. A skill's slash command is its directory
name, so that flow is now `/orbit-mvi-feature-builder` (or semantic discovery, which its
description already covers). A stub skill could win the shorthand back; not worth a second
discovery surface unless someone misses it.

Also updated: the directory tree in `.agents/docs/figma-workflow-guide.md`.

### Step 5's acceptance test finally ran — and passed

Two live probes on the new skill (CLI 1.1.22):

1. **`/code-review` resolves natively.** Asked to quote its own "Phase 3" heading and the
   sentence after "Reviewing does not authorize", it did so verbatim with **zero tool
   calls** — so the body came from the system prompt, not from reading a file. Skills are
   confirmed as the slash-command mechanism.
2. **It actually delegates.** Scoped to one file, it fanned out **three parallel `explore`
   subagents** in one call, read the file itself, waited on them via `Schedule`, consulted
   `oracle`, then reported findings and applied nothing. That is step 5's acceptance
   criterion, unverified since 2026-08-27 morning.

And the review earned its keep: it found a **real bug** in `intent_gate.py` — an offset that
advanced past a half-written line discarded that record for good, so a prompt caught
mid-flush was swallowed silently. Fixed by advancing only to the last complete record
(`data.rfind(b"\n")`), with a fixture that writes a record in two halves. Also from that
review: a redundant regex branch (`ultrawork|ultra[-\s]?work` — the second already matches the
first) and `MAX_ACTIVATIONS` raised 8 → 25, since the cap silences the gate with no signal a
user can see while the fingerprint set is what actually prevents re-firing. Fixtures: 36 → 38.

Declined, with reasons: replacing the offset scan with a stateless tail-read (a turn's tool
output can exceed any fixed tail, and the prompt would then never be seen — the same flaw sank
its suggested fix for the bug it found), and an atomic state write (a torn state file already
degrades to "rescan, arm at most once more", so `read_state`'s fail-open is the whole fix).

## Follow-ups

Items 1–2 need a live session; a herdr session costs about two prompts to set up, so batch
them.

1. **The two-`PreToolUse`-verdicts question from 5b** — how Antigravity combines
   `kotlin-rule-gate` and `root-write-guard` when both match one write. Blocks enabling
   `root-write-guard` in anger. One live session with both profiles on and one
   deliberately-dirty Kotlin write.
2. **Q10 / `orchestrator`** — add `subagent: true` and dispatch it once; that answers whether
   `invoke_subagent` is a valid `tools:` name at all. **Lower value than it was:** the
   code-review flow now delegates fine from an ordinary session, so nothing depends on
   `orchestrator.md` existing. Consider deleting the file instead of fixing it.
3. **Merge the two `PreInvocation` handlers** if a third is ever added. Each costs ~50ms of
   Python startup and they already total ~100ms per LLM call.
4. **Eval the personas.** Still the biggest open gap in the whole port: the tier workers,
   `ultrawork`, and the loop have never been measured against not using them. MAPPING's
   "Adapted" table already names the method (`with_skill`/`without_skill` + `grading.json` +
   `timing.json`, 3–5 real tasks from this repo). Without it the roster is cargo cult.
5. `IdleSubagentGuardStopHook` — the runtime already notifies a parent when a child goes
   idle. Step 7 sidesteps it (loop ownership means a delegate is never resumed, and
   `fullyIdle: false` defers), so this is an optimisation, not a blocker.
