# OMO → Antigravity Port Ledger

Working document for porting ideas from **oh-my-openagent** (OMO) into this
Antigravity workspace harness. Its job is to record what we decided *and what we
deliberately rejected*, so the port does not quietly grow into a runtime rewrite.

| | |
| :--- | :--- |
| Upstream | `https://github.com/code-yeongyu/oh-my-openagent` |
| Pinned reference | `b98042a30` (2026-08-27) |
| Local checkout | `oh-my-openagent/` → **Windows junction** to `D:\Quest\oh-my-openagent`. Its `.git/info/exclude` entry was removed 2026-08-27, so it now shows as `?? oh-my-openagent/` in `git status` — **never commit it** (it carries its own `.git`, so a stray `git add .` would add a gitlink). ⚠️ MSYS `ln -s` does **not** create a link on this machine, it silently deep-copies the target (51 entries, including `.git`); `ln -s` with `MSYS=winsymlinks:nativestrict` fails with *Operation not permitted* without developer mode. Use `New-Item -ItemType Junction -Path .\oh-my-openagent -Target D:\Quest\oh-my-openagent`. Steps 1–6 no longer read it; **step 8 does** |
| Test corpus | `CodebaseCompose/` → symlink to `/d/Quest/CodebaseCompose` (`com.genesys`, 90 `*.kt`, `core/designsystem` present). Gitignored. Used to validate hook false-positive rates |
| Upstream license | Sustainable Use License (internal business use OK; **no commercial redistribution**) |
| Reference docs | `docs/code_yeongyu_oh_my_openagent/` (DeepWiki export), `docs/antigravity/` |

## Framing

OMO is a **runtime** — a TS plugin for opencode/codex/senpi, ~40 packages, ~60
hooks, dynamically-built per-model prompts. This harness is **declarative** —
markdown + YAML that Antigravity interprets.

We port OMO's **process layer**. We keep our own **domain layer** (Compose,
Orbit MVI, Figma, Perfetto, R8 — OMO has none of it). The single most valuable
idea taken from OMO is not any prompt: it is **the orchestrator never writes code**.

Port scope: **level B** (patterns re-expressed natively) + the asset subset of
**level A** (domain-neutral skills) + **level C1** (enforcement hooks).
**Level C2** (runtime internals) is out of scope — see Rejected.

## Ledger

### Ported — near 1:1 onto native Antigravity mechanisms

| OMO concept | Antigravity mechanism | Notes |
| :--- | :--- | :--- |
| Discipline agents (`mode: primary`/`subagent`) | `.agents/agents/<name>.md` + `mainAgent`/`subagent` | Antigravity's execution symmetry is *better*: OMO needs `no-sisyphus-gpt`-style guard hooks, we just set `model:` |
| `task(subagent_type=…)` / `call_omo_agent` | `invoke_subagent` | direct |
| `run_in_background=true` | `manage_task`, background subagents, `/agents` + `/tasks` panels | direct; replaces OMO's tmux-core entirely |
| Skills (`SKILL.md` + `references/`) | identical format | OMO's `.agents/` and `packages/shared-skills/` are already agents.md-standard |
| Per-agent tool allow/deny (`agent-tool-restrictions.ts`) | `tools:` frontmatter | declarative instead of hook-enforced — a win |
| Per-agent skill scoping | `skills:` frontmatter | a win; OMO pays context for *all* skill descriptions |
| Plan-approval gates | `checkpoints.require_plan_approval`, `ask_question` | direct |
| `keyword-detector` / IntentGate | `PreInvocation` → `injectSteps[].ephemeralMessage` | ✅ **built** as `.agents/hooks/intent_gate.py`. **Gotchas:** the payload carries no prompt text (tail `transcriptPath`); match only inside `<USER_REQUEST>`, because `<ADDITIONAL_METADATA>` inlines the whole body of any slash-command skill; and stand down when the platform already activated the skill natively |
| `ralph-loop` / `ulw-loop` resume | `PostInvocation` → `terminationBehavior: "force_continue"` | |
| `todo-continuation-enforcer` (Boulder) | `Stop` → `decision: "continue"` + `reason` | ✅ **built** as `.agents/hooks/stop_verifier.py`. Better anchor than OMO's `session.idle` polling — and scoping it to "this conversation owns a loop directory" replaces OMO's session bookkeeping entirely |
| `plan-format-validator` | `PreToolUse` matched on write tools, path-filtered | **not** `PostToolUse` — that payload carries no `toolCall`, so it cannot know the target file |
| `comment-checker` | `PreToolUse` on the write tools → `deny` + reason | ✅ **built** as `.agents/hooks/rule_gate.py`. `PostToolUse` cannot do this: no `toolCall` in its payload. `PreToolUse` is also strictly better — it blocks the bad write instead of reporting it afterwards |
| `rules-injector`, `directory-readme-injector` | `PreInvocation` → `injectSteps` | |
| Write/read guards (`notepad-write-guard`, `prometheus-md-only`) | `PreToolUse` → `deny` | `tools:` frontmatter usually cheaper |
| ulw-loop `Spawn` guard (fan-out cap, gate-artifact check) | `PreToolUse` with `matcher: "invoke_subagent"` | our parallelism throttle |

### Adapted — same intent, different shape

| OMO concept | What we build | What changes |
| :--- | :--- | :--- |
| **Categories** (`CategoryConfig`) | one worker agent file per tier: `worker-quick`, `worker-deep`, (+ existing `figma-compose-developer` for visual) | `prompt_append` → agent.md **body**; `callerGuidance` → `description:`; `model`/`variant`/`reasoningEffort` → `model:`. This is OMO's own `file://` prompt_append mode with the indirection removed. Trim 8 categories → 3–4 tiers: more tiers than we have real model choices is theatre |
| **Ralph loop** | `.agents/state/loop/<conversationId>/` (goals + append-only `ledger.jsonl`) + `.agents/scripts/loop.py` CLI + SKILL.md + 3 hooks | OMO's loop is not runtime magic: it is *state dir + CLI the agent calls + hooks that read the state*. All four pieces exist here. Ledger progress — not turn count — is the stuck-detector |
| **Boulder brakes** | ✅ `.agents/hooks/stop_verifier.py` (re-derived, 52 fixtures, live-verified) | Hooks are stateless subprocesses, so cooldowns/counters live in our own state file keyed by `conversationId`. The algorithm was re-derived, not ported — see License. Two corrections to the shape assumed here: the hard-stop reasons are the real `TERMINATION_REASON_*` vocabulary (`max_steps_exceeded` does not exist), and compaction **tightens** the budget rather than suppressing, because surviving compaction is the loop's whole purpose |
| **Ultrawork** | ✅ `.agents/skills/ultrawork/SKILL.md` + `intent_gate.py` on `PreInvocation` | A **skill**, not a workflow — workflows are deprecated (see below), and skills are what serve `/<name>`. Rewritten, not lifted: 325 lines → 130. Kept the completeness pressure, dropped the maximalism and OMO's mandatory-commit discipline (this repo never commits unasked). The useful substitution: OMO's "GOAL REGISTRATION" *and* its `mktemp` durable notepad both collapse into `loop.py`, which already enforces the goal bar and is already enforced by step 7 |
| **Quality gate** | evidence artifacts the agent writes; hook *validates* rather than re-runs | Hooks block the agent loop synchronously — a `Stop` hook running Gradle costs 30–90s/turn against a 30s default timeout. Agent produces evidence → hook checks evidence |
| Discipline agent roster (11) | 5: `orchestrator`, `explore`, `oracle`, `worker-quick`, `worker-deep` | Metis+Momus merge (two agents for one review job is OMO bloat); Atlas+Sisyphus-Junior merge; drop Artistry (needs a provider we don't have), Multimodal-Looker, Librarian initially |
| Eval methodology | steal `with_skill`/`without_skill` + `grading.json` + `timing.json` from `.agents/skills/work-with-pr-workspace/` | Run 3–5 real tasks from our Android repo. Without this the personas are cargo cult |

### Rejected

| OMO concept | Why |
| :--- | :--- |
| `hashline_edit` (`hashline-core`) | **`PostToolUse` output schema is `{}` only.** Antigravity can rewrite tool *args* (`PreToolUse.overwrite`) but never tool *results*. Every OMO hook that enriches what the model sees back is unimplementable: also kills `hashline-read-enhancer`, `hashline-edit-diff-enhancer`, `read-image-resizer` |
| `model-fallback`, `runtime-fallback` | No model-selection control from hooks; single provider makes fallback chains moot |
| `preemptive-compaction`, `anthropic-context-window-limit-recovery` | No compaction event exposed (`PreCompact` exists in OMO's Claude-compat set, not in Antigravity's 5 events) |
| `background-notification`, `session-notification`, subagent lifecycle hooks | Antigravity exposes 5 events; OMO's compat layer has 12 (`SessionStart/End`, `SubagentStart/Stop`, `Notification`, `PreCompact`). No anchor point. **Mitigation:** the `Stop` handler checks for running children itself and returns `continue` |
| `memory-core` | Runtime; Antigravity's subagent isolation covers the context-hygiene motive |
| Team mode, `tmux-core` | Native background subagents + `/agents` panel replace the motive |
| Cross-provider category fallback chains, model registry gating | One provider |
| Model-conditional prompt variants (`resolvePromptAppend(model)`) | One provider. Where we do lift prose, use the `gemini.md` variants |
| A `omo-antigravity` harness adapter package (level C2) | Months of work against plugin APIs Antigravity does not document |

## Translation rules

When lifting any OMO markdown:

| OMO | Antigravity |
| :--- | :--- |
| `task(...)`, `call_omo_agent` | `invoke_subagent` |
| `read` | `view_file` |
| `write` | `write_to_file` |
| `edit`, `apply_patch` | `replace_file_content`, `multi_replace_file_content` |
| grep / glob | `grep_search`, `list_dir` |
| bash | `run_command` |
| `load_skills=[...]` | `skills:` frontmatter (dispatch-time, not call-time) |
| `task(category="deep")` | `invoke_subagent(worker-deep)` |

**Convention:** agents are flat files — `.agents/agents/<name>.md`, not
`<name>/agent.md`. Both forms are documented as discoverable; flat is chosen
because no agent carries sibling assets and the roster is about to double.
Filename must match the frontmatter `name:`. (Skills keep `<name>/SKILL.md` — there
the directory is load-bearing for `references/`.)

Also: keep `<Category_Context>` XML fencing (it separates the tier delta from the
host prompt); target **≤120 lines** per agent body and push the rest into skills —
300–500 line system prompts contradict the entire reason custom agents exist.

### Hook payload deltas (Claude Code / OMO compat ↔ Antigravity)

| | Claude Code / OMO | Antigravity |
| :--- | :--- | :--- |
| Casing | `snake_case` (`tool_name`, `tool_input`, `session_id`) | `camelCase` protojson (`toolCall.name`, `toolCall.args`, `conversationId`) |
| Prompt event | `UserPromptSubmit` (carries prompt text) | `PreInvocation` (**no prompt text** — tail `transcriptPath`) |
| Handler types | `command` + `http` | `command` only |
| Env control | `allowedEnvVars`, `pluginRoot` | none |

Considered: a `scripts/agy-hook-adapter.py` normalizing Antigravity stdin into the
Claude-Code payload shape, so handlers stay portable across ecosystems. **Deferred**
— revisit only if we end up with 4+ handlers or want to reuse third-party ones.

## Probe findings (2026-08-27, Antigravity CLI, `gemini-3.7-flash-high`)

107 hook records across 3 conversations: one `/figma-to-compose` main session, one
subagent it spawned, one unrelated concurrent human session.

### Confirmed

- **`PreInvocation` / `PostInvocation` / `Stop` all fire inside subagent contexts**
  (Q1 = **yes**), each with its **own** `conversationId`, brain dir, and transcript.
  Records interleave with the parent's in real time. Consequence: a naive
  `PreInvocation` injection lands in *every* agent in the tree, and a naive `Stop`
  enforcer would try to resume subagents.
- A subagent's `Stop` event effectively **is** the missing `SubagentStop` — in the
  child's own context. Partially recovers the gap listed under Rejected.
- **CWD = the directory containing `hooks.json`** (`…\AndroidHarnessAGY\.agents`),
  so `python hooks/probe.py` is the correct form. The `|| python .agents/…`
  fallback can be dropped.
- `PostInvocation` input == `PreInvocation` input, as documented. `Stop` swaps
  `initialNumSteps`/`invocationNum` for `error`/`executionNum`/`fullyIdle`/
  `terminationReason`.
- **Pre/Post are not strictly paired** (53 vs 51). Don't build state machines that
  assume pairing.
- Real model id format: **`gemini-3.7-flash-high`** — effort rides in the id
  (partial answer to Q4).
- **Doc inaccuracy:** transcripts are `…/logs/transcript_full.jsonl`, not
  `transcript.jsonl` as `05_lifecycle-hooks.md` claims. Both files exist; the
  payload points at `transcript_full`. Also chunked copies under `logs/chunks/`
  and per-step outputs under `steps/<n>/output.txt`.

### Transcript schema (intent gate is feasible)

Readable jsonl, **snake_case** (note: hook payloads are camelCase, transcripts are
not): `{type, source, content, created_at, status, step_index}`, plus `tool_calls`
and `thinking` on model records.

| field | values seen |
| :--- | :--- |
| `type` | `USER_INPUT`, `PLANNER_RESPONSE`, `GENERIC`, `SYSTEM_MESSAGE` |
| `source` | `USER_EXPLICIT`, `MODEL`, `SYSTEM` |

User prompts arrive as `type: USER_INPUT` / `source: USER_EXPLICIT`, content wrapped
in `<USER_REQUEST>` plus `<ADDITIONAL_METADATA>` and sometimes `<SKILL>` /
`<USER_SETTINGS_CHANGE>` tags.

**A delegated subagent's task prompt is also `USER_INPUT`/`USER_EXPLICIT` with
`<ADDITIONAL_METADATA>`** — identical in schema to a human message. Tested and
rejected as a discriminator.

### Parent/child discrimination

- The child's payload carries **no** parent pointer, agent name, or depth.
- The **child's `conversationId` appears in the parent's transcript**, and an unrelated
  session's does not. ⚠️ **But the relationship is recorded from both ends**, so a plain
  substring test is not a discriminator — it reports every parent as a child. Corrected
  2026-08-27 while building `write_guard.py`; the exact records are:

  | Direction | Record |
  | :--- | :--- |
  | parent, on spawn | `GENERIC`/`MODEL` — `Created the following subagents:\n{ "conversationId":  "<child>", …` |
  | child, on report | `GENERIC`/`MODEL` — `Message sent to "<parent>".` plus a `send_message` tool call |

  The working test is: *scan sibling brain dirs for a record containing **both** my
  `conversationId` and the literal `Created the following subagents`.* The spawn record is
  written before the child runs, so the signal is available from the child's first tool
  call. Measured ~15ms cold over 505 brain dirs (newest-first, capped) and 0.11ms once
  cached — cheap enough for `PreToolUse` on write tools, still too slow for every
  `PreInvocation`.
- **Better for the intent gate: don't discriminate at all.** Key off the last
  `USER_INPUT` matching the trigger regex. A subagent's task prompt won't say
  "ultrawork" unless the orchestrator wrote it there, so scoping is automatic.

### `invoke_subagent` shape (matters for the fan-out cap)

```json
{"Subagents": [{"Model": "inherit", "Prompt": "…"}]}
```

An **array** — fan-out is one tool call with N entries, so a `PreToolUse` matcher on
`invoke_subagent` can cap N in a single place. Both observed calls were *dynamic*
subagents (`Model` + `Prompt` only, no agent-name field); the shape when invoking a
**named** `.agents/agents/*` agent is still unknown.

### Anomaly

The parent issued **two** `invoke_subagent` calls but only **one** child
conversation produced hook records (the second call — its prompt matches the child's
first `USER_INPUT` verbatim). The first call may have been cancelled, rejected, or
failed. Unexplained; do not assume one spawn == one hooked conversation.

### `invoke_subagent` with a NAMED custom agent (Q7, answered 2026-08-27 via herdr)

Named agents **are** addressable. Observed args:

```json
{"Subagents": [{"Model": "inherit",
                "Workspace": "inherit",
                "TypeName": "figma-analyzer",
                "Role": "Figma Analyzer",
                "Prompt": "…"}],
 "toolAction": "Invoking Figma analyzer subagent",
 "toolSummary": "Invoke figma-analyzer subagent"}
```

`TypeName` is the frontmatter `name:`; `Role` is the display name. So tier dispatch is
`invoke_subagent(TypeName="worker-deep")` and **step 5's design holds**. The fan-out cap
reads `toolCall.args.Subagents` — an array, so N spawns arrive in one call.

### `tools:` is NOT the runtime tool set

A subagent asked to enumerate its own tools reported:

```
view_file, write_to_file, replace_file_content, grep_search, list_dir,
send_message, schedule, call_mcp_tool, list_resources, read_resource, manage_task
```

Only the first five are in its frontmatter. The runtime adds a base set —
communication (`send_message`), scheduling, MCP (`call_mcp_tool`, `list_resources`,
`read_resource`), and `manage_task` — regardless of what `tools:` says.

Two consequences:

1. **MCP access is automatic.** Listing `call_mcp_tool` in `tools:` does not grant it;
   it injects an invalid registry name and the agent then **fails to construct**:
   `failed to resolve components: unknown component: tool "call_mcp_tool" not found in registry`.
   Three of five agents were broken this way (`figma-analyzer`,
   `figma-asset-extractor`, `figma-ui-specialist`) — i.e. the entire Figma pipeline's
   named delegation was dead, which is why an earlier `/figma-to-compose` run fell back
   to dynamic prompt-only subagents. Fixed by deleting the line; verified by
   re-invocation.
2. **`tools:` is not a hard sandbox**, but the added base set contains no
   file-mutating tools — so the "orchestrator cannot write code" guarantee in step 5
   still holds via `tools:`.

Note what is **absent** from that base set: **`invoke_subagent` and `run_command`**. So an
agent that needs to delegate has to declare `invoke_subagent` itself (Q10 — unverified, and
the same class of risk that `call_mcp_tool` turned out to be), and `run_command` is the real
write escape hatch. Any agent holding `run_command` can mutate the tree through redirects,
`sed -i`, or `git checkout` regardless of what its file-tool list says. Consequence for step
5: the orchestrator holds **no** `run_command`, and `explore` — which does — is read-only by
instruction only, not by construction.

### Frontmatter keys beyond `name`/`description`/`model`/`tools`/`skills`

From doc `01_introducing-custom-agents.md`: `mainAgent`, `subagent`, `permissionMode`
(e.g. `acceptEdits`), and `commandExecutionPolicy` (`auto` lets an agent run build/test
commands unattended while destructive commands stay gated). The latter two are the right
knob for `worker-deep` under long-running autonomous work, but they loosen permissions, so
they are left unset until explicitly opted into.

### Failed subagents are invisible to hooks (closes Q8)

A subagent that fails to construct creates its brain dir and then **nothing** — zero
files, no transcript, no hook records. That was the earlier "two `invoke_subagent`
calls, one hooked conversation" anomaly. A spawn guard must therefore not assume
one spawn == one hooked conversation, and a `Stop`-time child check cannot rely on
child hook records existing.

### Design rule: keep non-gating hooks off the approval path

`PreToolUse` requires a `decision` for **every** matched call. A hook that only wants
to observe or manage side state therefore cannot use it without either downgrading an
auto-exec policy to prompting (`ask`) or silently auto-approving everything (`allow`).
`PreInvocation` and `Stop` have optional output and cannot affect approvals.

So: **`PreToolUse` only when the hook's job is to gate.** Everything else —
context injection, daemon/service lifecycle, loop continuation — belongs on
`PreInvocation`/`PostInvocation`/`Stop`. This is why `rule_gate.py` is `PreToolUse`
(it gates) and `scrcpy_daemon.py` is not (it manages a device daemon).

Corollary: hooks on `PreInvocation` run ~50×/session, so they must early-exit on
cheap state before doing any I/O. `scrcpy_daemon.py` does its work once per
conversation behind a marker file (~500ms), and every later invocation is a marker
check (~112ms, essentially Python startup). Verified end-to-end on a Pixel 7a,
including the refcount: a subagent's `Stop` leaves the daemon up, the last owner's
`Stop` takes it down.

## CLI introspection findings (2026-08-27, Antigravity CLI 1.1.22)

Established by non-interactive `agy` subcommands and by reading strings out of `agy.exe`
(186 MB Go binary at `%LOCALAPPDATA%\agy\bin\agy.exe`). Cheaper than driving a session —
try these before spending a real conversation on a question.

### `model:` frontmatter accepts ONLY `inherit` / `flash` — a full model id breaks the agent

Setting `model: gemini-3.7-flash-high` (a valid `--model` and `agy models` value) makes the
agent **fail to construct**, with the same symptom as a bad `tools:` entry:

```
Encountered error in tool execution: subagent "worker-quick" not found or not allowed to be invoked
```

Verified both directions in a live interactive session: with all ten agents pinned to
`gemini-3.7-flash-high`, *every* `invoke_subagent(TypeName=…)` failed — including
`figma-analyzer`, which was working an hour earlier. Reverting all of them to
`model: inherit` made all four tested types spawn and run. **Closes Q4** for practical
purposes: the frontmatter vocabulary is not the `agy models` vocabulary.

`inherit` is the right default anyway — the session model is already `gemini-3.7-flash-high`,
so `inherit` yields the intended model using a verified value. Differentiating tiers across
the 14 models is therefore **not** possible via `model:` alone with current knowledge.

Two lessons worth more than the fact itself:

- **This failure is silent until dispatch.** Nothing warns at startup, and `cli.log` does
  *not* log it (unlike a bad `tools:` name, which logs `not found in registry`). The only
  signal is the invocation error.
- **It looks identical to every other construction failure.** A bad tool name, a bad model
  value, and a genuinely missing agent all produce `not found or not allowed to be invoked`.
  When it appears, change one variable at a time.

### Flat vs directory agent layout: both work (Q closed)

Tested head-to-head with two throwaway agents — `.agents/agents/probe-flatform.md` and
`.agents/agents/probe-dirform/agent.md`. **Both constructed and replied.** So the flat-file
convention chosen under "Translation rules" is safe, and the earlier suspicion that the
`<name>/agent.md` → `<name>.md` rename broke discovery was wrong; that breakage was the
model-value bug above.

### `tools:` IS enforced for subagents — hard-verified

Dispatched `oracle` as a subagent and read the answer out of **its own** transcript rather
than the parent's relay:

```
NO_RUN_COMMAND_TOOL
Tools available: call_mcp_tool, grep_search, list_dir, list_resources,
                 manage_task, read_resource, schedule, send_message, view_file
```

Exactly `oracle`'s frontmatter (`view_file`, `grep_search`, `list_dir`) plus the runtime
base set. No shell, no write tools. This upgrades the earlier self-report to a real
finding: **the read-only guarantee is enforceable, via `tools:`, on the subagent path.**

Also confirms the base set precisely — `call_mcp_tool`, `list_resources`, `read_resource`,
`manage_task`, `schedule`, `send_message` — and that `invoke_subagent` is **not** in it
(so an agent that delegates must declare it), and that `call_mcp_tool` is auto-granted
even though declaring it breaks construction.

### `mainAgent: true` does not work via `agy --agent <name>` (CLI 1.1.22)

Three independent probes in a live interactive session started as
`agy --agent orchestrator`, with `model: inherit` and the agent file present:

1. Asked for the six delegation-prompt sections → answered from `worker-quick`'s
   `description:` instead, and explicitly denied a fixed section count exists.
2. Asked to complete a sentence unique to the orchestrator body → `NOT_PRESENT`.
3. Asked to run `git status --short` via `run_command` → **it ran it**, and returned real
   output. The orchestrator declares no shell.

So the body never reaches the system prompt and the full default toolset is present. The
CLI accepts `--agent <name>` and silently runs the default agent.

**Consequence for step 5:** the "orchestrator never writes code" invariant — the single
most valuable idea taken from OMO — is **not achievable as a main agent in the CLI today**.
It is achievable on the subagent path, where `tools:` demonstrably binds. Two options,
neither yet chosen:

- Add `subagent: true` to `orchestrator` and dispatch it as a subagent from an ordinary
  session. `tools:` then binds, but it is no longer the session driver.
- Accept that the process lives in the **workflow** file (`code-review.md`) rather than in a
  main-agent persona, and rely on tier subagents for the enforced boundaries. This matches
  what actually works today and needs no new mechanism.

Worth retesting on the Antigravity 2.0 desktop app, where custom agents are selected from a
dropdown — `mainAgent` may well work there and only be broken in the CLI.

### `--agent <name>` is ignored in `--print` mode

`agy --agent this-agent-does-not-exist-xyz --print "Reply with exactly: RAN"` returns `RAN`,
exit 0. The flag is not validated and the agent is not loaded, so **print mode cannot test
custom agents at all** — a trap for anyone scripting agent evals. Confirmed separately in a
real interactive session: `agy --agent orchestrator` also did not put the orchestrator body
in the system prompt (two independent probes), so main-agent selection via `--agent` remains
unverified even interactively. Named **subagent** dispatch does work, and that is what steps
5–8 depend on.

### `agy` has non-interactive subcommands

`agent`/`agents` (list agents), `models` (list models), `mcp`, `plugin`, plus flags
`--print`/`-p` (single non-interactive prompt), `--agent`, `--model`, `--effort low|medium|high`,
`--mode accept-edits|plan`, `--add-dir`, `--output-format text|json|stream-json`,
`--dangerously-skip-permissions`. `--print` with `--output-format stream-json` is the
scriptable surface if we ever want automated agent evals (step 5's eval methodology).

### The 14 available models (`agy models`)

```
gemini-3.7-flash-high / -medium / -low        gemini-3.6-flash-{high,medium,low}
gemini-3.5-flash-{high,medium,low}            gemini-3.1-pro-high / -low
claude-sonnet-4-6   claude-opus-4-6-thinking  gpt-oss-120b-medium
```

Effort rides in the id, and `--effort` exists separately. Consequence for step 5: real
tier differentiation is available (a Pro or Opus tier for `oracle`/`worker-deep`, a
flash-low tier for `worker-quick`/`explore`). **Currently all five are pinned to
`gemini-3.7-flash-high`** by owner decision; differentiating them is a later pass.

### `--agent <name>` fails SILENTLY

If the named agent is not discovered, the CLI runs the **default** agent with no warning
on stdout. A session that looks like it is running your custom agent may not be. This
invalidated a first round of testing here: the "orchestrator" happily reported a tool
list including `run_command`, `generate_image` and `search_web` — because it was the
default agent, not the orchestrator.

**Always identity-probe first**, before drawing any conclusion from behaviour:

> Quote verbatim the first two sentences under the '# Orchestrator' heading in your instructions.

A wrong answer means every other observation from that session is worthless. Corollary:
asking an agent to *enumerate* its tools proves nothing — it will produce a plausible
list either way. Ask it to *use* the tool and report the literal result.

### Workspace agents are not discovered in every context

`agy agent` returned empty and `invoke_subagent(TypeName='oracle')` returned
`subagent "oracle" not found or not allowed to be invoked` (with only `self` and
`research` available) in sandboxed non-interactive runs. `cli.log` explains why:
`Failed to resolve GeminiDir ".gemini": must be an absolute path, falling back to default`
and `You are not logged into Antigravity`. So **step-5 verification requires a real
interactive session in the workspace** — the same context in which the hook probe worked.

### Undocumented registry tools

Beyond the documented set: `define_subagent` ("defines a new type of subagent that can be
invoked via `invoke_subagent`" — a runtime alternative to `.agents/agents/*.md`),
`manage_subagents`, `find_by_name`, `ask_question`, `generate_image`, `read_url_content`,
`search_web`.

### Antigravity ships hidden built-in worker agents

`DeepCoder` and `DeepInvestigator`, invoked as
`invoke_subagent(TypeName='DeepCoder', Workspace='inherit')`. The binary states they are
**hidden from the subagents list but fully invocable**. Their built-in prompts use the
same spawn-and-wait pipeline shape we are building. `worker-deep` partly reinvents
`DeepCoder` — worth comparing before investing further in it.

### `IdleSubagentGuardStopHook` exists in the runtime

String: `IdleSubagentGuardStopHook: failed to send idle notification to parent %q`. So the
runtime already has a stop-hook that notifies a parent when a child goes idle. Relevant to
step 7's "don't resume while background children are still running" — there may be less to
build than assumed.

**Step 7 outcome:** sidestepped rather than used. `stop_verifier.py` only acts for a
conversation that *owns* a loop directory, so a delegate is never a candidate for resumption,
and `fullyIdle: false` defers the decision while anything is still in flight. Registering our
own named stop hook (`CustomizationConfig.stop_hook_names`, `stop hook %s not registered`)
remains unexplored.

## Workflows are deprecated — skills are the slash-command mechanism (step 8, 2026-08-27)

The single most consequential finding of the port, and it was sitting in the binary the whole
time. `agy.exe` contains a built-in skill, `migrate-workflows`, whose body reads:

> Workflows (`.agents/workflows/*.md` or `_agents/workflows/*.md`) are deprecated. Skills
> (`.agents/skills/<name>/SKILL.md` …) provide all the capabilities of workflows, plus:
> first-class slash command support (typing `/<name>` in the chat input box); semantic agent
> discovery (the agent can automatically invoke the skill when relevant); multi-file
> capabilities (supporting helper scripts, templates, and references).

Confirmed from the other end in a real transcript: `/figma-to-compose` arrived as
`<SKILL>The user has explicitly invoked the (figma-to-compose) skill…`, served from
`.agents/skills/figma-to-compose/SKILL.md` — **not** from the same-named workflow file, which
also existed in this repo and was therefore dead weight.

Consequences, in order of how much they hurt:

1. **It explained why step 5's acceptance test never ran.** Step 5 re-homed the orchestrator
   process into `.agents/workflows/code-review.md` and made `/code-review` the acceptance
   test — but with no `code-review` *skill*, the slash command had nothing to resolve to.
   Migrated the same day; `/code-review` now loads natively (verified by asking it to quote its
   own headings with zero tool calls) and delegates as designed (three parallel `explore`
   subagents, then `oracle`, then a report with no edits).
2. Any hook matching on prompt content must scope the match to `<USER_REQUEST>`. The
   `<ADDITIONAL_METADATA>` block that follows it inlines the **entire body** of the invoked
   skill, so a naive substring test fires on whatever that skill happens to mention.
3. Skill `description` fields are activation conditions, not summaries — semantic discovery
   reads them. This is also why the intent gate stays keyword-only: fuzzy activation is the
   description's job, and a regex for intent would fire on prose *about* rigour.
4. **All three workflow files are gone** (2026-08-27). Migrated by hand, not with the runtime's
   `migrate-workflows` skill, because only one wanted a 1:1 conversion: `code-review` became a
   skill; `figma-to-compose`'s unique content was its *orchestration*, folded into the existing
   skill as an "Upstream pipeline" section; `feature-orbit-mvi`'s was its domain/data phase,
   folded into `orbit-mvi-feature-builder` as "Stage 0". A duplicate skill is worse than a
   missing one — discovery then has to choose between them. Cost of the move: the
   `/feature-mvi` shorthand, since a skill's slash command is its directory name.

## `Stop` contract findings (step 7, 2026-08-27)

Established while building `stop_verifier.py` — from `agy.exe` strings, from the four real
Stop payloads in `state/probe.jsonl`, and from one live two-goal session driven through herdr.

### The documented `terminationReason` values do not exist

The payload carries the runtime's `TERMINATION_REASON_*` enum **minus the prefix**. Doc 05's
`model_stop` and PLAN's guessed `max_steps_exceeded` are both fiction. Observed in the wild:
`NO_TOOL_CALL`. The full vocabulary:

| Value | Read as |
| :--- | :--- |
| `NO_TOOL_CALL`, `TERMINAL_STEP_TYPE` | a normal model stop — the only reasons worth reversing |
| `EARLY_CONTINUE`, `INJECTED_RESPONSE` | not a termination at all; the loop is already continuing |
| `ERROR`, `HALTED_STEP`, `USER_CANCELED` | something already went wrong or the human said no |
| `MAX_INVOCATIONS`, `MAX_FORCED_INVOCATIONS`, `MAX_TOKEN_BUDGET_EXCEEDED` | a runtime budget is spent — resuming fights the runtime |
| `UNSPECIFIED` | unset |

`executionNum` was **0** on all four observed Stops — not a usable turn counter. Use ledger
progress instead (which is why `loop.py`'s `ledger_seq` is dense and monotonic).

### The runtime has its own continuation cap

`CascadeExecutorConfig.max_stop_hook_continuations`, with a changelog entry: "Fixed stop hooks
that always block hanging the agent forever; after a configurable number of consecutive
continuations, the hook can no longer block and the turn ends normally." Neighbouring fields:
`max_nominal_continuations`, `max_error_continuations`. **The value is not readable from
here**, so it is a backstop and not a substitute for your own brakes.

### A `continue` verdict is visible in the transcript

It lands in the agent's own transcript as `type: SYSTEM_MESSAGE`, `source: SYSTEM`, wrapped in
`<SYSTEM_MESSAGE>` and prefixed by the runtime with `Stop hook blocked termination: `
(matching the binary's `stop hook blocked termination due to reason: %s`). Consequences:
write `reason` as a standalone instruction, and remember that anything a hook injects becomes
part of the corpus the *next* transcript-reading hook scans.

`{"decision": "stop"}` is confirmed safe as the permit value — `probe.py` returned exactly
that on four real Stops and every session ended normally.

### Injected content is visible, and typed distinctly (step 8)

A `PreInvocation` `injectSteps[].ephemeralMessage` lands in the transcript as
`type: EPHEMERAL_MESSAGE`, `source: SYSTEM_SDK` — two vocabulary values missing from the
schema recorded under "Probe findings". Neither an injected ephemeral message nor a `Stop`
continuation is ever a `USER_INPUT`, so a content-injecting hook that filters on record type
cannot re-trigger itself. Its marker text *does* still show up in `GENERIC`/`MODEL` tool
results when an agent reads the hook's own source or `hooks.json` — one more reason to filter
on type rather than on content alone.

### Compaction is detectable, verbatim

The runtime injects: `**The earlier parts of this conversation have been truncated due to its
long length. The following content summarizes the truncated context so that you may continue
your work. **` — so "has this session been compacted" is a substring test on the transcript,
no event needed. (Doc-set gap: `PreCompact` has no Antigravity equivalent, and this is the
closest thing to a signal.)

### `$ANTIGRAVITY_CONVERSATION_ID` is real, `$AGY_CONVERSATION_ID` is not

Live-verified: the agent printed `ANTIGRAVITY_CONVERSATION_ID` from inside `run_command`, and
the value matched both its brain dir and the hook payload's `conversationId`. This closes
step 6's "session id is the loose joint": `loop.py`'s state directory is named after the
conversation. `AGY_CONVERSATION_ID` does not appear anywhere in the binary — the first
candidate in `loop.py`'s resolution chain is dead weight (harmless, left in place).

### Where the plan was wrong to suppress on compaction

The plan said to suppress resumes entirely under context pressure. The loop exists *precisely*
to survive compaction, so `stop_verifier.py` instead tightens the per-goal budget to one and
leads the injected reason with "run `loop.py status --json` first". An amnesiac that then does
nothing is caught by the ledger-advance check, which is the same brake by a cheaper route.

## Open questions

| # | Question | Blocks | Status |
| :--- | :--- | :--- | :--- |
| 1 | Does `PreInvocation` fire inside **subagent** contexts? | dynamic category injection; whether the intent gate reaches workers | ✅ **yes** — see Probe findings |
| 2 | Is there a per-agent `hooks:` frontmatter key? Blog doc 01 says custom agents scope "skills, MCP servers, and hooks" but documents no key | per-agent gating | open — now *more* valuable, since it would solve parent/child scoping declaratively |
| 3 | Actual payload shape + CWD resolution on Windows under `cmd /c` | all hook work | ✅ **answered** — see Probe findings |
| 4 | Valid `model:` values beyond `flash` / `inherit` | tier workers | ✅ **answered 2026-08-27, the hard way.** `agy models` lists 14 real models, but the **frontmatter accepts only `inherit` / `flash`** — a full model id makes the agent fail to construct. All agents are on `model: inherit`; since the session model is `gemini-3.7-flash-high`, that *is* the intended model. Per-tier model differentiation is not achievable through `model:` with current knowledge |
| 7 | `invoke_subagent` arg shape when targeting a **named** custom agent | spawn guard; whether tier workers are addressable by name | ✅ **answered** — `TypeName`/`Role`/`Model`/`Workspace`/`Prompt`; see above |
| 8 | Why did one of two `invoke_subagent` calls produce no hooked conversation? | fan-out accounting in the spawn guard | ✅ **closed** — the subagent failed to construct; failed spawns leave an empty brain dir and emit no hook records |
| 9 | Argument shape of `replace_file_content` / `multi_replace_file_content` (only `write_to_file`'s `TargetFile` is documented) | precision of the rule gate on edits, not just whole-file writes | instrumented — `rule_gate.py` logs unrecognised shapes to `.agents/state/rule_gate_unknown_args.jsonl` and passes through; check that file after a session with Kotlin edits |
| 5 | Does this harness ever ship outside the company? If yes: write tier bodies **clean-room** from behavior descriptions, do not adapt OMO prose | sourcing for tier bodies + ultrawork | ✅ **decided 2026-08-27 — internal only.** Adapting OMO prose is permitted under the Sustainable Use License's internal-business-use grant. Step 5 bodies were adapted from `openai-categories.ts`, `explore.ts`, `oracle.ts`, and `sisyphus-dynamic-prompt-{role,execution}.ts`. If the ship decision ever reverses, these five files are the derivative work to rewrite |
| 6 | Ultrawork tone vs `ponytail.md` — its maximalism ("deliver the FULL implementation", "no simplified versions") directly contradicts our YAGNI rule | ultrawork content | ✅ **decided 2026-08-27 — completeness, not maximalism.** Keep the finishing pressure ("requested scope, delivered and verified — no stubs, no TODOs"); drop "FULL implementation", "no simplified versions", "maximum thoroughness". `ponytail.md` remains the sole authority on *how much* to build. The resolution is already written into `worker-deep.md` under "Completeness, not maximalism" — reuse that wording in `ultrawork.md` |
| 10 | Is `invoke_subagent` a valid `tools:` registry name? It is **not** in the runtime base set, so the orchestrator must declare it — but declaring a name absent from the registry is how `call_mcp_tool` broke three agents | whether `orchestrator` constructs | **still open.** `orchestrator` is the one step-5 agent not yet dispatched as a subagent (it is `mainAgent: true`, and main-agent selection via `--agent` could not be confirmed working). Supporting evidence: `invoke_subagent` occurs 68× in `agy.exe` next to `define_subagent`, vs exactly once for known-invalid `call_mcp_tool`. **How to check:** `grep "not found in registry" ~/.gemini/antigravity-cli/cli.log` — a bad tool name is logged there verbatim (a bad *model* value is not) |
| 11 | Does `mainAgent: true` work at all? | the no-write invariant, i.e. all of step 5's premise | ❌ **no — not via `agy --agent <name>` in CLI 1.1.22.** Verified three ways: the body never enters the system prompt and the session keeps the full default toolset. Worse than "opt-in": unavailable. `tools:` *is* enforced on the subagent path, so the invariant must move there or into the workflow file. Retest on the 2.0 desktop app |

## Order of work

> Steps 5–8 are specified for handoff in [`PLAN.md`](PLAN.md), including the platform
> facts a fresh session should not re-derive and the herdr verification recipe.

1. ~~Repo hygiene — exclude the nested clone~~ ✅
2. ~~This document~~ ✅
3. **Hook contract probe** — 🔧 *installed, awaiting first real session.*
   `.agents/hooks.json` (profile `omo-port-probe`) + `.agents/hooks/probe.py`.
   Logs every payload to `.agents/state/probe.jsonl` (gitignored) and always emits
   a safe no-op directive. Verified against synthetic payloads: safe output per
   event, survives empty/garbage stdin, and the `python .agents/… || python …`
   form resolves from both candidate CWDs.
   `PreToolUse` is deliberately **not** probed — its `decision` field is required,
   so a probe would have to return either `allow` (silently disabling permission
   prompts) or `ask` (spamming them). Learn that payload later, while building the
   spawn guard.
   **To read results:** `python -c "import json;[print(json.loads(l)['event'], json.loads(l).get('payload_keys')) for l in open('.agents/state/probe.jsonl')]"`
   **Off switch:** set `"enabled": false` in the profile. **Remove entirely** once
   Q1/Q3 are answered here — answers Q1, Q3.
4. ~~**Rules-as-gates**~~ ✅ `.agents/hooks/rule_gate.py`, profile `kotlin-rule-gate`, **enabled**.
   Three rules: `kotlin-comment` (KDoc exempt), `hardcoded-string` (user-facing Compose
   params), `raw-hex-color` (exempt `:core:designsystem` and `@Preview` regions).
   `PreToolUse` → `deny` with per-line reasons; fails open on error, non-Kotlin target,
   or unrecognised arg shape. Self-verifying: `--self-test` (13 fixtures),
   `--scan <path>` (corpus sweep).
   *Acceptance met:* 13/13 fixtures; **0 false positives** over 90 files in
   `CodebaseCompose`. Precision on the string rule 6/6.
   **Baseline in the existing codebase:** 54 `//` comments (11 files) and 6 hardcoded
   user-facing strings already violate these rules. The gate only inspects *agent
   writes*, so legacy code is untouched — but the number is worth knowing.
   **False-positive class found and removed:** Compose `label =` is animation tooling
   (`animateFloatAsState`, `rememberInfiniteTransition`, `animateFloat`), not
   user-facing text; it produced only false hits and is excluded.
   *Pass verdict* is `ask`, which preserves the normal approval flow and respects
   cached "Always Allow". Flipping `PASS_DECISION` to `allow` auto-approves clean
   Kotlin writes — a real UX change, opt in deliberately.
5. ~~**Tier workers + process agents**~~ ✅ **written 2026-08-27** — `orchestrator`, `explore`,
   `oracle`, `worker-quick`, `worker-deep` in `.agents/agents/`, plus a rewrite of
   `code-review` to actually delegate (it was a four-phase solo workflow; the acceptance test
   was untestable against it). That file later moved to `.agents/skills/code-review/SKILL.md`
   — workflows are deprecated — and the acceptance test passed there on 2026-08-27.
   Bodies 51–102 lines, all under the 120 cap. Frontmatter parses; filenames match `name:`.
   **Decisions applied:** orchestrator gets **no `run_command`** — with a shell it could
   write files via redirects, and the no-write invariant would drop back to prompt-level
   discipline that no hook can enforce. All git inspection is delegated to `explore`, which
   holds `run_command` under a read-only instruction.
   `commandExecutionPolicy: auto` (a real frontmatter key, doc 01) was deliberately **not**
   set on either worker — it is a permissions loosening that should be opted into knowingly.
   *Not yet verified:* no Antigravity session was live, so construction is unconfirmed —
   see Q10, and the Verification recipe in PLAN.md
5b. ~~**Top-level write guard**~~ ✅ **built 2026-08-27.** `.agents/hooks/write_guard.py`,
   profile `root-write-guard`, **disabled by default**. Denies writes to *source* files when
   the calling conversation is the root session; passes them for delegates. Docs and notes
   are never gated — the invariant is about code, and a root session that cannot write a plan
   is useless at the job it is supposed to do.
   *Acceptance met:* a delegate writes while its parent cannot, verified on 3 real
   conversation ids plus 31 fixtures. ~15ms cold across 505 brain dirs, 0.11ms cached.
   Escape hatch needs no config edit: `write_guard.py --off` / `--on` / `--status`.
   **The detection had to be directional, and this is the finding worth keeping:** the
   parent/child relationship is recorded from *both* ends —
   `Created the following subagents:\n{ "conversationId": "<child>"` in the parent, and
   `Message sent to "<parent>"` plus a `send_message` tool call in the child. A plain
   "does another transcript mention my id" test therefore reports **every parent as a
   delegate**. The working test requires the child's id and the spawn marker in the *same*
   record. The earlier note under "Parent/child discrimination" was right that the mention
   exists, and wrong that it is one-directional.
   Only `delegate` is cached; `root` is the verdict inferred from absence, which is also what
   a not-yet-flushed parent looks like, so caching it would make an early misread permanent.
6. ~~**Loop state + CLI**~~ ✅ **built 2026-08-27.** `.agents/scripts/loop.py`
   (`create-goals`, `status`, `checkpoint`, `steer`, `reconstruct`, `--self-test`) +
   `.agents/skills/loop/SKILL.md`. State at `.agents/state/loop/<session>/`:
   append-only `ledger.jsonl` (authoritative) + `goals.json` (derived cache, atomic write).
   *Acceptance met:* `reconstruct --check` fails when the cache drifts from the ledger, and
   deleting the cache entirely loses nothing — both asserted in the fixture suite (35/35).
   **The CLI fails loud**, unlike the hooks: a hook that blocks work on its own bug is worse
   than one that misses a violation, but a *CLI* that silently half-records progress lets the
   agent believe evidence exists when it does not.
   The goal quality bar from OMO's `define-goal.md` is enforced **mechanically** — activity-only
   objectives, unfalsifiable pass conditions, missing `stop_when`, and criteria without
   `expected_evidence` are all rejected at `create-goals` time rather than being advice in a
   prompt. That is the one place this port improves on OMO rather than translating it.
   Session id resolves `--session` → `$AGY_CONVERSATION_ID` → `$ANTIGRAVITY_CONVERSATION_ID`
   → `default`; whether Antigravity sets either env var is **unverified**, so step 7's hook
   (which does get `conversationId`) may need a reconciliation step.
   Two Windows bugs found by testing rather than review, both now fixtures: a cp1252 console
   raising `UnicodeEncodeError` mid-print *after* the ledger write (fixed by reconfiguring
   stdout to UTF-8), and PowerShell's `Out-File -Encoding utf8` BOM breaking `--goals-json`
   (fixed by reading input files as `utf-8-sig`).
7. ~~**`stop_verifier.py`, brakes first**~~ ✅ **built 2026-08-27.** `.agents/hooks/stop_verifier.py`,
   profile `stop-verifier`, **enabled** — and inert unless the stopping conversation owns a
   loop under `.agents/state/loop/`, which is what scopes it to the main session without any
   parent/child detection at all.
   Eleven brake conditions, every one of which exits by *permitting* the stop; the resume path
   is the last branch, not the first. Stuck detection is **ledger progress**, never turn count.
   Verification validates the *record* — a `complete` goal sitting on a non-zero recorded exit
   code, a missing evidence artifact, or `goals.json` drifting from the ledger each block the
   stop, and no build ever runs inside the hook.
   *Acceptance met:* 52 fixtures, including "a productive-but-unfinished loop resumes at most
   twice, then permits for good" and "a resume that produced no ledger entry is stuck, not
   resumed again". ~51ms/Stop with no loop registered, ~70ms worst case over a 6MB transcript.
   **Live-verified** on a two-goal session: one resume then a clean permit; and an
   unsatisfiable goal closed out as `failed` on the record rather than ground on.
   New platform facts in "`Stop` contract findings" above — the documented
   `terminationReason` values do not exist, and `$ANTIGRAVITY_CONVERSATION_ID` closes step 6's
   session-id question.
8. ~~**Intent gate + ultrawork**~~ ✅ **built 2026-08-27.** `.agents/skills/ultrawork/SKILL.md`
   (a **skill**, not the planned workflow — workflows are deprecated, see above) plus
   `.agents/hooks/intent_gate.py`, profile `ultrawork-intent-gate`, **enabled**.
   The gate turns the literal word `ultrawork` / `ultra work` / `ulw` in a user prompt into an
   injected directive. Cost discipline matters here because `PreInvocation` fires ~50×/session:
   the transcript is append-only, so it stores a byte offset per conversation and scans only the
   delta — steady state is a `stat` plus a 256-byte head check, i.e. **~50ms of pure Python
   startup**; a full first scan of a 1MB transcript is 65ms. Fires once per prompt
   (fingerprinted), capped at 8 per conversation, matches only inside `<USER_REQUEST>`, and
   stands down when `/ultrawork` already loaded the skill natively.
   Q6 applied as decided; also dropped OMO's mandatory-commit discipline, which contradicts this
   repo's "never commit unasked".
   *Verified:* 36 fixtures, plus live — the agent was injected once, read the skill with
   `view_file`, opened with `ultrawork:`, classified the request **research**, and changed
   nothing.

## License note

Sustainable Use License permits internal business use; it forbids commercial
redistribution, requires notices to be preserved, and requires modified copies to
be marked. Practical consequence: hook handler *logic* lifted from
`todo-continuation-enforcer` is derivative work, while the *algorithm* described in
the DeepWiki chapter is not. Where behavior is simple enough to re-derive (~80
lines for the Boulder brakes), **re-derive it**. Q5 was decided 2026-08-27 (internal use
only), and `stop_verifier.py` was re-derived regardless — its brake set diverges from
OMO's anyway, because Antigravity's real `terminationReason` vocabulary and our
ledger-owns-the-loop scoping have no OMO counterpart.
