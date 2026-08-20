---
name: ui-android-compose
description: Specialized skill for building UI with Jetpack Compose, managing resources, and following Android best practices.
---
# jetpack-compose-ui

This skill is specialized for implementing user interfaces (UI) with Jetpack Compose in Android.
It inherits UI/UX design principles from `ui-ux-pro-max` but focuses on code organization, resource management, and Jetpack Compose-specific best practices.

## 1. Workflow

When receiving a request to build UI for Android with Compose:
1. **Analyze Design**: Review Design System, layout, colors, typography (usually provided from ui-ux-pro-max skill).
2. **Structure Composables**: Break down interface into small, reusable `@Composable` functions. Follow *Stateless by default* principle (hoist state to parent).
3. **Manage Resources**: Check and reuse existing resources (colors, strings, icons). Extract new values to configuration files.
4. **Implement UI**: Use Modifier and standard layouts (`Column`, `Row`, `Box`, `LazyColumn`) along with basic Compose components.
5. **Integrate logic**: Connect to ViewModel/Data layer through event callbacks, don't include business logic in Composables.

## 2. Resource Management (NO Hardcode Rule)

This is the most critical rule when working with Android UI:

| Rule | Do                                                                                                                                                   | Don't |
|------|------------------------------------------------------------------------------------------------------------------------------------------------------|----- |
| **No hardcoded values** | Extract strings, colors, fonts, and dimensions to corresponding files (`res/values/strings.xml`, `res/font/`, `Color.kt`, or constant file).           | Hardcode strings (`"Hello"`), colors (`Color(0xFF0000)`), fonts, or dimensions directly in UI code. |
| **Reuse Assets & Resources** | **MINIMIZE USE OF ANDROID'S BUILT-IN ICON/STRING/COLOR/DIMEN. BROWSE PROJECT RES DIRECTORIES TO FIND SUITABLE RESOURCES FIRST. IF AVAILABLE USE IT, ONLY USE ANDROID'S IF NOT AVAILABLE.** | Use Android/Material icons/colors/strings directly without checking project resources. |
| **Use AppTheme (Don't use MaterialTheme)** | Use the design system's `AppTheme` design tokens (e.g., `AppTheme.colorScheme.colorText`, `AppTheme.spacing.md`). | Use standard `MaterialTheme` or define isolated color constant files. |
| **Use Icons** | **MANDATORY** browse for suitable icons in `drawable` directory first. Only when TRULY NOT AVAILABLE use `Icons` from compose material/Android default. | Always use `Icons.Default...` or `@android:drawable/...` without checking `drawable`. |

## 3. Jetpack Compose Best Practices

| Rule | Do | Don't |
|------|----|----- |
| **State Hoisting** | Push state up to parent component, pass value (`value`) down and receive event (`onValueChange`) from child. | Keep local state `remember { mutableStateOf() }` in components that need to be reused or shared. |
| **Modifiers** | Use Modifier for alignment, padding. Prioritize Modifier order (e.g., padding before background vs background before padding). | Wrap with extra layouts (`Box`, `Column`) just to add padding. |
| **Lazy Layouts** | Use `LazyColumn`/`LazyRow` for long or dynamic lists. | Use `Column` + `verticalScroll` for very long lists reducing performance. |
| **Recomposition** | Use `derivedStateOf` when calculating state frequently (like `listState.firstVisibleItemIndex`). | Recalculate heavy values in every recomposition loop. |
| **Side Effects** | Use correct side effects: `LaunchedEffect` (run suspend), `DisposableEffect` (need cleanup), `rememberCoroutineScope` (only for UI events). | Initialize coroutines randomly in Composable body. |
| **Lifecycle** | Collect state using Orbit's specialized `collectAsState()` extension from `org.orbitmvi.orbit.compose`. | Collect raw `stateFlow` manually with `collectAsStateWithLifecycle()` or use non-lifecycle-aware standard Compose `collectAsState()`. |
| **Previews** | Must create `@Preview` function for each screen (Screen) or main component to display UI visually (encourage passing mock data). | Build UI without creating Preview, forced to run app to see design. |

## 4. Pre-Delivery Checklist (Compose Specific)

Before completing Compose code, check:

### Resources & Assets
- [ ] NO hardcoded text strings. All text uses `stringResource()`.
- [ ] NO hardcoded colors. All colors from AppTheme color tokens.
- [ ] Dimensions (dp, sp) referenced from resources if needed.
- [ ] Fonts referenced from Typography system or standard resource, not randomly initializing fonts directly.
- [ ] Checked `res/drawable` directory for suitable icons before using Compose `Icons`.
- [ ] Checked `res/values/` and `res/font/` directories to reuse existing images/strings/fonts.

### Architecture & Performance
- [ ] Main screens (Screen level) only receive UI State and pass events to ViewModel.
- [ ] Child Components are all Stateless (receive properties, return events).
- [ ] No layouts nested excessively unnecessarily.
- [ ] Lists always use `LazyColumn` / `LazyRow` with appropriate `key` for items.

### Interface (UI/UX)
- [ ] Ripple effect and Hover/Click states work correctly (ensure clickable/tappable elements have feedback).
- [ ] Interface supports both Dark Mode and Light Mode well (check colors in both modes).
- [ ] Support accessibility: Use `contentDescription` for all meaningful images and icons.
- [ ] Have `@Preview` function for each screen (Screen) and important Components, containing mock data.
