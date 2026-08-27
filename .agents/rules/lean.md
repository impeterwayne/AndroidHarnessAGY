---
trigger: always_on
---

# Lean Engineering Rule: Pragmatic Minimalism & YAGNI

Apply the "Lazy Senior Developer" mindset across all coding, refactoring, and architectural tasks:

## 1. The Decision Ladder (Climb before writing code)
1. **YAGNI First**: If a feature or parameter is speculative, do not implement it.
2. **Reuse First**: Check for existing helper methods, Base classes, Design System components (`AppButton`, `AppText`, `AppPanel`), theme tokens (`AppTheme`), and MVI patterns before writing new ones.
3. **Kotlin Stdlib & KTX**: Use built-in functions (`let`, `takeIf`, `filterNotNull`, `buildList`, `collectAsStateWithLifecycle`, etc.) instead of writing custom utility functions.
4. **Jetpack Compose & Android Native First**: Use Compose design system primitives, VectorDrawables, and native platform features before reaching for external dependencies.
5. **Shortest Idiomatic Form**: Use Kotlin single-expression functions, `when` expressions, and null-coalescing (`?:`) to keep logic concise.

## 2. Anti-Patterns to Reject
- No interfaces with only one implementation (unless mocking in unit tests requires it).
- No single-class factory/builder patterns when default arguments or direct instantiation suffice.
- No boilerplate scaffolding "for future requirements".
- No fixing symptoms in multiple caller sites when one root-cause fix at the source handles all callers.

## 3. Strict Non-Negotiables (Lazy $\neq$ Careless)
- **Null Safety**: Always enforce strict Kotlin null safety.
- **Resources**: Never hardcode UI strings — always use `res/values/strings.xml`.
- **Comments**: Never add unnecessary comments in Kotlin code (`//`, `/* */`).
- **Architecture**: Preserve Clean Architecture / MVVM / MVI contracts.
