---
name: lean-debt
description: >
  Harvest every `lean:` marker in the codebase into a tracked debt ledger,
  preventing deliberate shortcuts and deferrals from being forgotten.
  Use when the user asks for "lean debt", "/lean-debt", "what did we defer",
  "list shortcuts", or "lean ledger".
---

# Lean Debt (Shortcut & Deferral Tracker)

Collect all deliberate shortcuts, simplifications, or deferred items marked in the codebase into a clean, trackable ledger.

## Scan Protocol

Scan the workspace for `lean:` markers (e.g. in comments or docstrings):

`grep -rnE '(#|//|/\*) ?lean:' .`

(Exclude build artifacts, `build/`, `.gradle/`, `.git/`).

## Output Table Format

| File & Line | Shortcut / Deferral | Ceiling / Upgrade Trigger |
| :--- | :--- | :--- |
| `path/to/File.kt:42` | Direct Glide load without custom transformation | Add when complex multi-source cache is required |
