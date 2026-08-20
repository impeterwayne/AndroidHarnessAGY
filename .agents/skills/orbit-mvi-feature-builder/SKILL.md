---
name: orbit-mvi-feature-builder
description: Build Orbit MVI feature flows for AI Mental Math using the canonical pokedex feature and repo architecture rules. Use when the user asks to implement a new screen, feature flow, route, contract, ViewModel, stateless Compose screen, or graph in this codebase.
---

# AI Mental Math Orbit MVI Feature Workflow

## Overview

Implement or extend Android UI feature flows in the AI Mental Math codebase using the repository's canonical Orbit MVI pattern.

Use this skill when work involves any of the following:
- creating a new feature screen or flow
- scaffolding or modifying a type-safe route in `:core:navigation`
- creating or updating a `[Feature]Contract.kt`
- creating or updating a `[Feature]ViewModel.kt`
- creating or updating a stateless `[Feature]Screen.kt`
- extracting feature UI blocks into `components/`
- wiring a `[Feature]Graph.kt` with Orbit state and side-effects

Do not use this skill when the request is limited to:
- data, database, or network layer work with no feature UI changes
- build or environment setup only
- documentation-only work

**Primary reference:** `docs/feature_implementation.md`

**Canonical implementation anchor:** `:feature:pokedex`

## Conventions

- Bare paths (e.g. `references/guide.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory.
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- Treat `:feature:pokedex` as the gold-standard implementation unless the user explicitly instructs otherwise.
- Prefer repository-local conventions over generic Android or Orbit MVI examples.

## On Activation

### Step 1: Load Project Context

Inspect these sources before making structural decisions:
- `{project-root}/docs/feature_implementation.md`
- `{project-root}/docs/architecture.md`
- `{project-root}/docs/navigation.md`
- the target implementation in `:feature:pokedex`

### Step 2: Identify Scope

Resolve or ask for the minimum needed implementation scope:
- feature/module name
- screen or flow name
- route name and route arguments
- whether this is a root screen, detail screen, or multi-screen flow
- required use cases or domain dependencies
- whether cross-feature navigation is involved

If a required detail is missing and cannot be safely inferred from neighboring features, ask before implementing.

### Step 3: Find the Closest Existing Pattern

Inspect the nearest comparable feature module and `:feature:pokedex`. Use the closest valid local pattern first, then fall back to the pokedex.

### Step 4: Enter the Workflow

Execute the workflow stages below in order. Skip only stages that are genuinely out of scope for the request.

## Workflow

### Stage 1: Define or Update the Route

Work in `:core:navigation` and ensure route boundaries are type-safe and shared at the core layer.

**Must do:**
- Add or update the route in `Route.kt`.
- Use `@Serializable` and `@Parcelize`.
- Use `data object` for no-argument destinations.
- Use `data class` for destinations with arguments.
- Keep route definitions in the shared navigation layer so features do not depend on each other directly.

**Must not do:**
- Do not define feature-local route types outside `Route.kt` when the route belongs in shared navigation.
- Do not introduce string-based route handling when the repo uses typed routes.

**Success criteria:**
- Route type exists in `:core:navigation` and matches the needed screen flow.

### Stage 2: Define the MVI Contract

Create or update `[Feature]Contract.kt` in the feature presentation package.

**Must do:**
- Define immutable `UiState`.
- Define `Action` for user intent and lifecycle triggers.
- Define `SideEffect` for one-off events such as navigation, snackbars, dialogs, or transient UI instructions.
- Keep naming consistent with the feature and neighboring modules.

**Must not do:**
- Do not encode one-off navigation or transient effects as persistent screen state.
- Do not let the contract leak infrastructure concerns unrelated to presentation behavior.

**Success criteria:**
- The contract clearly separates state, intent, and one-off effects.

### Stage 3: Implement the ViewModel

Create or update `[Feature]ViewModel.kt` using the project-standard Orbit MVI structure.

**Must do:**
- Inherit from `BaseViewModel<UiState, SideEffect, Action>`.
- Inject dependencies with Hilt.
- Define the Orbit `container` with the initial state.
- Route incoming actions through `onAction`.
- Use `intent { ... }` blocks for mutations and side-effects.
- Use `reduce { state.copy(...) }` for state transitions.
- Use `postSideEffect(...)` for one-off events.
- Handle asynchronous work using repository-standard flow and result patterns.

**Must not do:**
- Do not mutate state outside Orbit intent/reduce flow.
- Do not push navigation decisions directly into stateless screen composables.
- Do not bypass the established result handling pattern used by neighboring features.

**Success criteria:**
- ViewModel owns feature behavior, state transitions, and one-off effects in the same style as `:feature:pokedex`.

### Stage 4: Implement the Stateless Screen

Create or update `[Feature]Screen.kt` as a pure rendering layer.

**Must do:**
- Accept a single state object and explicit callbacks.
- Render loading, success, and error states consistently with the repo's UI patterns.
- Use the project design system components and tokens.
- Keep the composable previewable where appropriate.

**Must not do:**
- Do not inject a Hilt ViewModel into the stateless screen.
- Do not pass navigation controllers into the stateless screen.
- Do not perform navigation directly from the rendering layer.
- Do not couple the screen to graph-level orchestration.

**Success criteria:**
- The screen is stateless, previewable, and driven entirely by inputs.

### Stage 5: Extract Feature Components

Use a `components/` package for nontrivial UI blocks.

**Must do:**
- Extract lists, cards, hero panels, and reusable UI blocks out of the main screen file.
- Reuse `AppPageFrame`, `AppPanel`, `AppText`, and other design-system primitives where applicable.
- Keep component APIs small and explicit.

**Must not do:**
- Do not leave large inline UI sections in the main screen when they reduce clarity.
- Do not substitute raw Compose primitives for project-specific design-system equivalents without a good reason.

**Success criteria:**
- The main screen remains readable and orchestration-free, and complex UI is isolated in components.

### Stage 6: Wire the Feature Graph

Create or update `[Feature]Graph.kt` as the navigation and orchestration boundary.

**Must do:**
- Hoist the ViewModel with `hiltViewModel()` at the graph boundary.
- Collect Orbit state with the project-standard compose integration.
- Collect side-effects and translate them into navigator actions.
- Map typed route entries with `entryProvider`.
- Render the active stack with `NavDisplay`.

**Must not do:**
- Do not move graph responsibilities into the stateless screen.
- Do not perform route mapping in unrelated files.
- Do not mix cross-feature orchestration into a feature unless the app-level wiring pattern explicitly requires it.

**Success criteria:**
- Graph owns routing, state collection, side-effect handling, and route-to-screen mapping.

### Stage 7: Handle Cross-Feature Navigation Correctly

If the flow reaches screens in other feature modules, follow the repository navigation architecture.

**Must do:**
- Use app-level orchestration when feature modules must remain decoupled.
- Pass injected composable lambdas or callbacks from the `app` layer when required.
- Keep module boundaries clean.

**Must not do:**
- Do not create direct feature-to-feature dependencies that violate module boundaries.

**Success criteria:**
- Navigation remains type-safe and modular without circular dependencies.

### Stage 8: Validate Before Completion

Before considering the work complete, verify the implementation against the repo rules.

**Validation checklist:**
- [ ] Required module dependencies are present.
- [ ] Route exists in `Route.kt` and uses typed navigation conventions.
- [ ] Contract defines `UiState`, `Action`, and `SideEffect`.
- [ ] ViewModel uses Orbit `container`, `intent`, `reduce`, and `postSideEffect` correctly.
- [ ] Screen is stateless and contains no direct ViewModel or navigation leakage.
- [ ] Complex UI has been extracted into `components/` where appropriate.
- [ ] Design system primitives and tokens are used consistently.
- [ ] Graph owns ViewModel hoisting, state collection, side-effects, and route mapping.
- [ ] Cross-feature navigation, if present, respects app-level boundaries.

## Guardrails

- Always inspect `:feature:pokedex` before implementing a new feature flow.
- Prefer the closest local feature pattern when it is clearly valid and consistent with the architecture.
- Keep changes minimal and scoped to the requested flow.
- Preserve typed navigation, stateless rendering, and graph-level orchestration boundaries.
- Use repository patterns first; do not import generic patterns that conflict with local architecture.
- If the user request conflicts with core architecture rules, surface the conflict before implementation.

## Output

When using this skill successfully, the final outcome should include:
- the list of created or changed files
- the route, contract, ViewModel, screen, component, and graph decisions made
- the validation steps completed
- any unresolved assumptions, follow-ups, or required user decisions
