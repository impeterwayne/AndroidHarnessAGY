---
name: ui-android-compose
description: Specialized skill for building UI with Jetpack Compose, organizing Composables, managing state, and adhering to Android best practices. Use alongside android-resource-policy for resource management.
---
# jetpack-compose-ui

This skill is dedicated to building (implementing) user interfaces (UI) with Jetpack Compose in Android.
It focuses on Compose code organization, state management, lifecycle handling, performance, accessibility, and previews. When handling strings, colors, icons, fonts, drawables, or Android resources, also apply the `android-resource-policy` skill.

## 1. Workflow

When receiving a request to build Android UI with Compose:
1. **Design Analysis**: Review the Design System, layout, colors, typography, and required UI states.
2. **Composable Decomposition**: Break down the UI into small, reusable `@Composable` functions. Follow the *Stateless by default* principle (hoist state to the parent).
3. **Resource Management**: Use `android-resource-policy` to inspect and reuse existing resources before adding new ones.
4. **UI Implementation**: Use Modifiers and standard layouts (`Column`, `Row`, `Box`, `LazyColumn`) along with core Compose components.
5. **Logic Integration**: Connect to ViewModel/Data layer via event callbacks; avoid business logic inside Composables.
6. **Preview Creation**: Create `@Preview` functions for each Screen and key Component with mock data.

## 2. Jetpack Compose Best Practices

| Rule | Do | Don't |
|------|----|-----|
| **State Hoisting** | Hoist state to parent components, pass `value` down, and receive events (`onValueChange`) from children. | Keeping local state `remember { mutableStateOf() }` inside reusable or shared components. |
| **Saveable State** | Use `rememberSaveable` for UI state that needs to survive configuration changes or process recreation. | Using plain `remember` for critical state like active input, selected tabs, or enabled filters that need restoration. |
| **Stable UI State** | Pass immutable/stable UI state; prefer immutable data classes and collections without direct mutation. | Passing mutable list/map/state objects and mutating them directly inside Composables. |
| **Modifiers** | Use Modifiers for alignment and padding. Prioritize Modifier chaining order (e.g., padding before background vs. background before padding). | Wrapping redundant layouts (`Box`, `Column`) solely to apply padding. |
| **Lazy Layouts** | Use `LazyColumn` / `LazyRow` for long or dynamic lists. | Using `Column` + `verticalScroll` for excessively long lists, causing performance degradation. |
| **Recomposition** | Use `derivedStateOf` for frequently calculated state (such as `listState.firstVisibleItemIndex`). | Recalculating heavy computations on every recomposition cycle. |
| **Side Effects** | Use appropriate side effects: `LaunchedEffect` (suspending work), `DisposableEffect` (cleanup needed), `rememberCoroutineScope` (UI events only). | Spawning coroutines arbitrarily inside Composable bodies. |
| **Lifecycle** | Collect ViewModel flows using `collectAsStateWithLifecycle()`. | Using `collectAsState()`, which can leak memory or keep collecting data while in the background. |
| **Previews** | Always create `@Preview` functions for each screen or major component to inspect UI visually (with mock data). | Building UI without Previews, forcing a full app run to inspect design. |
| **Localization & Scale** | Design UI to accommodate long text, large font scale, and RTL when multi-language support is required. Use plurals/formatted strings properly. | Fixing width/height causing text truncation or manually concatenating strings. |

## 3. Pre-Delivery Checklist (Compose Specific)

Before finalizing Compose code, verify:

### Resources & Assets
- [ ] Applied `android-resource-policy` for strings, colors, icons, drawables, fonts, and dimensions.
- [ ] Static text uses string resources; dynamic text from state/API/input is not placed in `strings.xml`.
- [ ] UI remains intact with long text, large font scale, and RTL if supported.

### Architecture & Performance
- [ ] Main screens (Screen level) only consume UI State and propagate events to ViewModel.
- [ ] Child components are Stateless (receive properties, emit events).
- [ ] State requiring restoration uses `rememberSaveable` or is hoisted to ViewModel/UI state.
- [ ] UI state passed into Composables is immutable/stable; collections are not mutated directly in Composables.
- [ ] No unnecessary deeply nested layouts.
- [ ] Lists always use `LazyColumn` / `LazyRow` with stable item `key`s.

### UI / UX
- [ ] Ripple effects and tap/click states function properly (clickable/tappable elements have visual feedback).
- [ ] `@Preview` functions are provided for each Screen and key Component with mock data.
