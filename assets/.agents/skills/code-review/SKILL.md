---
name: code-review
description: >
  Audits modified code for over-engineering, missed reuse, architectural compliance, design
  token usage, and Android intent security — delegating discovery to `explore` and judgement
  to `oracle`, and reporting rather than fixing unless asked. Use when the user says "review
  code", "review the diff", "audit this change", "check architecture", "look for
  over-engineering", or asks whether a change is ready to merge.
metadata:
  short-description: Delegated review of the working diff, findings first
---

# code-review

You scope, synthesize and verify. Discovery, judgement and any fixes are delegated — not
because you cannot read code, but because a review that fits in one context is a review that
skimmed. Read the changed files yourself before drawing any conclusion: never review a diff
you have not read.

Reviewing does not authorize changing. Findings first; edits only if the user asks for them.

Pairs with the [`lean-review`](../lean-review/SKILL.md),
[`android-resource-policy`](../android-resource-policy/SKILL.md) and
[`android-intent-security`](../android-intent-security/SKILL.md) skills — load whichever the
diff actually touches.

## Phase 1 — Scope (delegate to `explore`, in parallel)

Fire three `explore` subagents in **one** `invoke_subagent` call — `Subagents` is an array:

1. **Diff scope** — `git status` and `git diff --stat` against the merge base. Return the
   changed files grouped by Gradle module, with the line count per file.
2. **Dependency direction** — for each changed module, read its `build.gradle.kts` and report
   any dependency that crosses a Clean Architecture boundary the wrong way (feature → data,
   domain → framework, core → feature).
3. **Resource and manifest surface** — every `stringResource`/`R.string` reference, literal
   string in a Compose text parameter, raw hex colour, and `exported="true"` component
   introduced by the diff.

Then read the changed files with `view_file` before moving on.

## Phase 2 — Judgement (delegate to `oracle`)

Send `oracle` the changed files plus Phase 1's findings. Ask for three things, in this order
of priority:

- **Over-engineering** — interfaces with one implementation, single-class factories and
  builders, wrapper classes that add no behaviour, speculative parameters, scaffolding for
  requirements nobody asked for.
- **Missed reuse** — custom code where `core/designsystem`, an existing use case, an
  `AppTheme` token, or a Kotlin stdlib/KTX function already does the job.
- **Contract risk** — anything that breaks an Orbit MVI contract, a ViewModel signature, a
  navigation argument, or an analytics trigger.

Split this across two parallel `oracle` calls when the diff spans more than about five
modules; one consultation per coherent area beats one that skims everything.

## Phase 3 — Rule compliance (yourself, directly)

Cheap to check by reading, so do not pay for a subagent:

- Every user-facing string resolves through `res/values/strings.xml`.
- Every colour resolves through `AppTheme.colorScheme` — exceptions are `:core:designsystem`
  and `@Preview` code only.
- No added Kotlin comments (`//`, `/* */`) outside KDoc on public API.
- Newly exported manifest components have an explicit permission or signature check.

The `kotlin-rule-gate` hook already blocks *agent* writes that violate the first three, so
findings here are almost always in code a human wrote. Report them; do not assume they are the
agent's.

## Phase 4 — Report

One report, ordered most severe first. Per finding: the file and line, what is wrong in a
sentence, and the concrete change that fixes it. Separate confirmed problems from suggestions.
Attribute pre-existing issues as pre-existing.

Say plainly when nothing significant turned up. A short honest review beats a padded one, and
inventing findings to look thorough is the failure mode here.

## Phase 5 — Fixes, only if asked

If the user asks for the findings to be applied:

- One-file mechanical fixes (extract a string, swap a hex for a token, delete a comment) →
  batch them into parallel `executor` calls, one file each, each prompt naming the file and
  the single edit so none of them goes exploring.
- Anything structural (removing an abstraction, redirecting a dependency, changing a contract)
  → one `executor` call per coherent change, with the module's compile and test commands
  named as the required evidence.

Then verify: re-read each changed file, and check the evidence the executor reported. A
subagent's summary of what it did is not evidence that it did it.
