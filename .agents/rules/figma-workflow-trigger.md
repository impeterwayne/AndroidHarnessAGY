---
trigger: always_on
---

# Figma Integration & Workflow Trigger Rule

Whenever the user's prompt or message contains a **Figma URL** (e.g., `https://www.figma.com/design/...`, `https://www.figma.com/file/...`, `https://figma.com/...`) or specifies a **Figma node-id** / screen name:

## Mandatory Execution Protocol:

1. **AUTOMATIC SKILL ACTIVATION**:
   - Immediately activate and follow the `figma-design-analyzer` skill (and `figma-to-compose` for UI implementation).
   - Do NOT skip to writing code or making guesses without inspecting the Figma node.

2. **PARSE FIGMA URL & NODE ID**:
   - Extract the file key and `node-id` parameter from the URL.
   - Note: URLs encode colons as `%3A` or `-` (e.g. `node-id=123%3A456` or `node-id=123-456`). Convert this to the standard `123:456` format for MCP tool queries.

3. **EXECUTE FIGMA MCP CALLS (`figma_mcp_android`)**:
   - Query the target node using `get_design_context` (use `depth: 2` or `3`, `detail: "compact"`, `dedupe_components: true` to conserve tokens).
   - Extract typography and text using `scan_text_nodes`.
   - Extract design tokens, color palette, and spacing using `get_styles` / `export_tokens`.
   - Extract prototype interactions using `get_reactions`.
   - For simple vector icons: convert SVG to VectorDrawable XML in `res/drawable/ic_*.xml` via `convert_svg_to_android_drawable`.
   - For raster illustrations/graphics/banners: export directly to `app/src/main/assets/images/` via `save_screenshots`.

4. **OUTPUT & IMPLEMENTATION**:
   - For new screens / specs: generate `docs/<feature>/figma-spec.md` or present the UI structure.
   - For UI implementation: follow `figma-to-compose` (using `com.genesys.core.designsystem.theme.AppTheme` design tokens, design system components, and Skydoves Landscapist `GlideImage`), ensuring strict adherence to the extracted tokens, dimensions, and colors while preserving existing ViewModel/business logic.
