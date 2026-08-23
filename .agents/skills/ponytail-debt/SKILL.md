---
name: ponytail-debt
description: >
  Harvest every `ponytail:` marker in the codebase into a tracked debt ledger,
  preventing deliberate shortcuts and deferrals from being forgotten.
  Use when the user asks for "ponytail debt", "/ponytail-debt", "what did we defer",
  "list shortcuts", or "ponytail ledger".
---

# Ponytail Debt (Shortcut & Deferral Tracker)

Collect all deliberate shortcuts, simplifications, or deferred items marked in the codebase into a clean, trackable ledger.

## Scan Protocol

Scan the workspace for `ponytail:` markers (e.g. in comments or docstrings):

`grep -rnE '(#|//|/\*) ?ponytail:' .`

(Exclude build artifacts, `build/`, `.gradle/`, `.git/`).

## Output Table Format

| File & Line | Shortcut / Deferral | Ceiling / Upgrade Trigger |
| :--- | :--- | :--- |
| `path/to/File.kt:42` | Direct Glide load without custom transformation | Add when complex multi-source cache is required |
