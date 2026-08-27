---
name: figma-to-compose
description: Inspects Figma design node, extracts VectorDrawable assets & tokens, and builds stateless Compose UI following Clean Architecture and Orbit MVI.
trigger:
  slash_command: /figma-to-compose
  keywords:
    - "figma.com/design"
    - "figma.com/file"
    - "implement screen from figma"
agents:
  - figma-analyzer
  - figma-asset-extractor
  - figma-compose-developer
skills:
  - figma-design-analyzer
  - figma-asset-extractor
  - figma-to-compose
  - android-resource-policy
  - orbit-mvi-feature-builder
---

# Figma to Jetpack Compose Workflow

## Phase 1: Design Context Inspection
- Parse the target node-id and file key from the user-provided Figma URL.
- Dispatch figma-analyzer subagent to invoke get_design_context (depth: 2, detail: "compact", dedupe_components: true).
- Extract typography, Auto-Layout constraints, paddings, color hex values, and component hierarchies.
- Identify existing code structure using android-code-indexer.

## Phase 2: Asset & Token Extraction
- Dispatch figma-asset-extractor subagent.
- Batch convert simple vector icons (24-48dp) into res/drawable/ic_<name>.xml via convert_svg_to_android_drawable.
- Map color codes and typography sizes to com.genesys.core.designsystem.theme.AppTheme.
- Export raster banners/artwork to assets or remote URL placeholders.

## Phase 3: Orbit MVI Contract Derivation
- Define the screen contract in <Feature>Contract.kt:
  - UiState: Strongly-typed data class representing visual elements.
  - UiAction / UiEvent: Sealed interface representing user interactions.
  - SideEffect: Sealed interface for one-off navigation/snackbars.

## Phase 4: Stateless Compose Implementation
- Dispatch figma-compose-developer subagent.
- Implement stateless @Composable function <Feature>Screen(uiState: UiState, onAction: (UiAction) -> Unit).
- Use design system tokens (AppTheme.colorScheme, AppTheme.typography, AppTheme.spacing).
- For image loading, integrate Skydoves Landscapist GlideImage.
- Implement @Preview composables for Light, Dark, and Loading states.
- Connect to @HiltViewModel via Route.kt.

## Phase 5: Verification & Quality Gate
- Ensure no hardcoded strings or raw hex colors exist.
- Verify adherence to Clean Architecture and Orbit MVI conventions.