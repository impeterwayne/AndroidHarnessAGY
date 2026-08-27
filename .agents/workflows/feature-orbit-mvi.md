---
name: feature-orbit-mvi
description: Scaffolds and implements an end-to-end Orbit MVI feature flow across Clean Architecture layers.
trigger:
  slash_command: /feature-mvi
  keywords:
    - "create feature"
    - "new orbit flow"
    - "implement feature"
skills:
  - orbit-mvi-feature-builder
  - android-code-indexer
---

# Feature Flow Workflow (Clean Architecture + Orbit MVI)

## Phase 1: Domain & Data Contracts
- Define Domain Models in :core:model.
- Define Repository Interface in :core:domain.
- Define UseCases in :core:domain (single responsibility, operator fun invoke).
- Implement Repository in :core:data coordinating Network ApiService and Room DB.

## Phase 2: Feature Module Scaffolding
- Create/update :feature:<name> module structure.
- Define Contract.kt (UiState, UiAction, SideEffect).
- Implement ViewModel.kt (@HiltViewModel, ContainerHost<UiState, SideEffect>, intent { reduce { ... } }).

## Phase 3: UI & Routing
- Implement Stateless <Feature>Screen.kt.
- Implement Navigation <Feature>Route.kt bridging navigation backstack and ViewModel state collection.
- Register destination in :core:navigation.

## Phase 4: Verification
- Verify Clean Architecture boundary constraints (no direct data/network dependency from feature).
- Audit code simplicity with Ponytail guidelines.