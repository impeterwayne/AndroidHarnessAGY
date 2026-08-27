---
name: lean-audit
description: >
  Whole-repo audit for over-engineering. Scans the entire codebase instead of a single diff,
  producing a ranked list of what to delete, simplify, or replace with stdlib/Android native equivalents.
  Ranked by biggest potential code reduction first.
  Use when the user asks to "audit this codebase", "audit for over-engineering", "find bloat",
  "what can I delete from this repo", or invokes /lean-audit.
---

# Lean Audit (Repo-Wide Bloat & Complexity Scan)

Perform a whole-codebase scan hunting unnecessary abstractions, redundant utility classes, unused boilerplate, and reinventions of Kotlin standard library / Android Jetpack APIs.

## Audit Output Format

Rank findings starting with the **biggest cuts first** (e.g. entire redundant classes/modules before single methods).

### Tags:
- `delete:` Dead code, unused layers, redundant wrapper classes, speculative features. *(Replacement: delete / inline)*.
- `stdlib:` Hand-rolled logic that Kotlin standard library or Android KTX already provides. *(Name the stdlib/KTX feature)*.
- `native:` Custom UI or widgets that can be replaced with built-in Android / Material components.
- `yagni:` Abstraction with one implementation, config with single constant values, or unused flexibility.
- `shrink:` Verbose boilerplate that can be reduced to idiomatic Kotlin expressions.

## Non-Negotiable Guards
Do not flag necessary safety features:
- Kotlin Null Safety & safe calls (`?.`, `?:`).
- `strings.xml` resource references.
- MVVM / Clean Architecture boundaries (ViewModels, UseCases, Repositories).
