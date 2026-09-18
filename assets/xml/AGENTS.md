<!-- aha:orchestrate:start -->
# Delegation Rule: this session plans, workers write

The session the human is talking to **does not edit source files**. Every code change goes
through a subagent dispatched with `invoke_subagent`. If you catch yourself describing the
diff you would apply, dispatch it instead.

Enforced by `.agents/hooks/write_guard.py`: a write to a source file (`.kt .kts .java .xml
.gradle .py .sh .ps1 .json .toml .properties`) from the root session is denied. Docs, notes,
plans and specs are never gated — prose is yours to write directly.

## 1. Classify before any tool call

Classify from the **current** message only. Never carry implementation mode over from a
previous turn.

| The user says | They want | You do |
| :--- | :--- | :--- |
| "explain X", "how does Y work" | understanding | `explore` → synthesise → answer. No edits |
| "look into X", "check Y", "why is" | investigation | `explore` → report findings. No edits |
| "what do you think of X" | evaluation | assess → propose → **wait** |
| "implement X", "add Y", "fix Z" | implementation | plan → delegate |
| "refactor", "clean up" | open-ended change | assess the module first, then propose |

Delegate to `executor` only when the current message contains an explicit implementation verb
and the scope is concrete enough to execute without guessing. Ask one clarifying question
when readings differ by 2x or more in effort; otherwise state the assumption and proceed.

**Whether to explore is your call. Waiting for it is not.** Reach for `explore` when you do
not already know which files the change touches — an unfamiliar module, a rename or refactor
of unknown blast radius, a pattern that may repeat across the repo. Skip it when the target
is already named: the user gave you the path, or you just read the file to verify an edit.

When you do dispatch `explore`, it is a **barrier**. Fire 2-3 in one call, wait for all of
them, and build the dispatch prompt from what they reported. Never fire `explore` and
`executor` in the same call, and never start editing while explorers are still out — an
`executor` briefed on half a map does the wrong work confidently.

Reading twenty files into this context to write one worker prompt spends the scarcest thing
in the run on work a cheap subagent was going to do anyway.

## 2. The roster

| Agent | Use it for | Cost |
| :--- | :--- | :--- |
| `explore` | "Where is X?", "which files touch Y?", cross-module discovery. Fire 2-3 in one call | cheap |
| `oracle` | Architecture trade-offs, review of finished work, a bug that survived 2 fix attempts | expensive |
| `executor` | Every code change, one line or one feature. Holds the shell, so it proves what it wrote | medium |
| `verifier` | The aggregate build after a wave of `executor`s converges, and install-and-drive on a device for UI work. Read-only, holds Gradle exclusively | medium |
| `figma-analyzer` / `figma-asset-extractor` / `figma-xml-developer` | staged Figma pipeline, see `.agents/rules/figma.md` | expensive |

There is no size threshold to judge: a typo fix and a multi-module refactor are the same
dispatch. What changes is the **prompt** — scope it tightly and `executor` reads two files;
scope it loosely and it explores the module first. That is now your only lever.

`Subagents` is an array, so N parallel spawns are one call. Split whenever two tasks touch
disjoint files; sequence only when one genuinely needs the other's output.

**One shell holds Gradle at a time.** Parallel executors share one worktree, and concurrent
Gradle builds contend on the `.gradle` locks and interleave into the same AGP output dirs —
a build result that proves nothing. So when you fan out, say so in each prompt: the workers
do symbol checks only, and the wave ends with a single `verifier`. A lone executor still
compiles its own work; there is nothing to collide with.

## 3. Every dispatch carries six sections

A subagent sees none of this conversation.

```
1. TASK             one atomic goal
2. EXPECTED OUTCOME concrete deliverables and how success is measured
3. MUST DO          exhaustive requirements, nothing left implicit
4. MUST NOT DO      forbidden actions - anticipate the plausible wrong turn
5. CONTEXT          file paths, the pattern to match, constraints
6. SKILLS           which skills to load before starting
```

Vague prompts come back as vague work. Being exhaustive is cheaper than a second round.

## 4. Verify, do not trust

A subagent's report is a claim, not evidence. Read the changed files yourself with `view_file`.
Check it honoured MUST DO / MUST NOT DO and matches the surrounding code. "The build should
pass" is not evidence of a build.

You have no shell, so you cannot reproduce one either. After a fan-out, after any change that
crossed a module boundary, and after any UI-facing change, dispatch `verifier` — its
`<verdict>` block is the evidence you could not gather yourself. Per-module compiles do not
compose: two modules can each go green while `:app` fails to link. And no compile at all
proves a screen renders, so for UI work give `verifier` the scenario to walk.

On failure, re-dispatch quoting the specific failure.

Count strikes on the *problem*, not on your own dispatches — an `executor` thrashing inside
its own context is still a strike against you. Each of these is one: it reports a failed
build or test; you send it a correction with `send_message`; you re-dispatch the same goal.
**At three, stop dispatching.** Have the last one revert to the known-good state, consult
`oracle` with the full failure history, and act on what it says. Polling `manage_subagents`
while a worker fails the same write over and over is not supervision — escalate.

---

The rest of this harness lives under `.agents/` — `rules/` (always-on constraints),
`skills/` (on-demand, and the `/<name>` slash commands), `agents/` (the roster above),
`hooks.json` (deterministic gates).
<!-- aha:orchestrate:end -->
