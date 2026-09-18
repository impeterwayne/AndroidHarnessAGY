---
name: lean-review
description: >
  Code review focused exclusively on hunting over-engineering, bloat, speculative abstractions,
  and dead code in Android/Kotlin codebases. Returns ultra-concise, line-by-line findings
  specifying what to delete, simplify, or replace with stdlib/framework features.
  Use when the user asks for a simplification review, "what can we delete", "is this over-engineered",
  or invokes /lean-review.
---

# Lean Review (Complexity & Bloat Hunter)

Review code diffs, classes, or PRs specifically for over-engineering and unnecessary complexity. The best review outcome is a shorter diff and fewer lines of code.

## Review Output Format

Provide single-line findings in the following format:
`<file>:L<line>: <tag> <what to cut>. <replacement>.`

### Tags:
- `delete:` Dead code, unused parameters, speculative features, or redundant wrapper classes. (Replacement: *nothing / delete*).
- `boundary:` Wide interface smell. Function or Composable taking $>4$ parameters instead of splitting responsibilities or passing a well-shaped value.
- `layer:` Unnecessary manager/handler/adapter/factory added to do one thing. Collapse or remove.
- `stdlib:` Hand-rolled logic that Kotlin standard library or Android KTX already provides. (Name the stdlib function/KTX extension).
- `native:` Custom UI or logic that can be replaced with built-in Android / Material components.
- `yagni:` Abstraction with one implementation, config with a single constant value, or unused flexibility.
- `shrink:` Verbose logic that can be simplified into idiomatic Kotlin expressions or fewer lines.

## Guidelines
- Prioritize high-impact cuts (negative diffs > entire layers/classes > single methods > expressions).
- **The Fence**: Do not suggest removing error handling, null safety, string resource extractions, or necessary architecture boundaries.
