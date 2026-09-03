---
trigger: always_on
---

# Lean Engineering Rule: Pragmatic Minimalism, YAGNI & Radical Simplicity

Apply the "Lazy Senior Developer" and George Hotz radical simplicity mindset across all coding, refactoring, and architectural tasks:

> *"Complexity is the enemy. You can always make your software do more. The magic is when you can make your software do more without adding complexity — because complex things eventually collapse under their own weight."*

- **LOC is debt, not output.** More capability at equal or lower complexity is the only win. Adding a feature by adding a layer is a loss. A negative diff is the gold standard.

## 1. The Decision Ladder (Climb before writing code)
1. **Delete & Collapse First**: Before touching a subsystem, ask *"Can this not exist?"* Collapse duplicated logic to one source of truth and delete the glue that kept copies in sync.
2. **YAGNI First**: If a feature, parameter, or config flag is speculative or hypothetical, do not implement it.
3. **Reuse First**: Check for existing helper methods, Base classes, Design System components (`AppButton`, `AppText`, `AppPanel`), theme tokens (`AppTheme`), and MVI patterns before writing new ones.
4. **Kotlin Stdlib & KTX**: Use built-in functions (`let`, `takeIf`, `filterNotNull`, `buildList`, `collectAsStateWithLifecycle`, etc.) instead of writing custom utility functions.
5. **Jetpack Compose & Android Native First**: Use Compose design system primitives, VectorDrawables, and native platform features before reaching for external dependencies.
6. **Shortest Idiomatic Form**: Use Kotlin single-expression functions, `when` expressions, and null-coalescing (`?:`) to keep logic concise.

## 2. Anti-Patterns & Complexity Smells
- **Layer Sprawl**: Introducing a new manager/handler/factory/adapter/wrapper to do one thing $\to$ stop, ask what to remove or collapse instead.
- **Wide Interfaces**: A wide interface is a design signal. If a function or Composable is growing toward $\sim 4-5$ parameters, treat the boundary as suspect. Fix the boundary (split responsibilities or pass one well-shaped value) — never hide width behind an options/params bag.
- **Single-Implementation Interfaces**: No interfaces with only one implementation (unless mocking in unit tests requires it).
- **Single-Class Factories/Builders**: Direct instantiation or Kotlin default arguments suffice.
- **Speculative Scaffolding**: No methods, parameters, or flags "for future requirements".
- **Symptom Patching**: No fixing symptoms in multiple caller sites when one root-cause fix at the source handles all callers.

## 3. Understand the Whole Stack (Nothing is Magic)
- Build the smallest runnable unit. Inspect real runtime values and state rather than assuming what they "should" be.
- Read definitions and callsites before concluding. Never assert code "works" or "is safe" without seeing it.
- AI-generated code must be read and validated line-by-line; speed is never correctness.

## 4. Strict Non-Negotiables & The Fence (Lazy $\neq$ Careless)
- **The Fence**: Prove code is truly dead before deleting (check all callsites); scope deletion to what the task touches; never delete a real invariant (money, auth, data-integrity, lifecycle, resource loading, error states) to "simplify" — that is a bug.
- **Null Safety**: Always enforce strict Kotlin null safety (`?.`, `?:`, smart casts, exhaustive `when`).
- **Resources**: Never hardcode UI strings — always use `res/values/strings.xml`.
- **Comments**: Never add unnecessary comments in Kotlin code (`//`, `/* */`).
- **Architecture**: Preserve Clean Architecture / MVVM / MVI contracts.
