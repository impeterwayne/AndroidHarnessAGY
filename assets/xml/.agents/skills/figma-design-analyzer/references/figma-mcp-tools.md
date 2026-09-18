# Figma MCP Tools Reference & Best Practices

MCP Server: `figma_mcp_android`

## 1. Tool Catalog & Capabilities

| Tool | Purpose | Key Parameters | When to Use |
|---|---|---|---|
| `get_selection` | Get IDs and names of currently selected nodes in Figma | None | **First step** when user says "look at my selection in Figma". |
| `get_design_context` | Token-efficient tree traversal of selection or active page | `depth` (number, default 2), `detail` ('minimal'\|'compact'\|'full'), `dedupe_components` (boolean) | **Primary layout exploration tool**. Replaces `get_document` to prevent token blowout. |
| `get_node` | Deep inspection of a specific node | `nodeId` (e.g. '1234:5678'), `depth` | When you need full details (layout, fills, effects) of a specific sub-tree. |
| `get_nodes_info` | Inspect multiple nodes in a single call | `nodeIds` (array of strings) | Comparing or verifying multiple component variants or siblings. |
| `scan_nodes_by_types` | Filter sub-tree for specific node types | `nodeTypes` (`['FRAME', 'COMPONENT', 'TEXT', 'VECTOR', ...]`), `depth`, `detail` | Finding all vector icons, buttons, or text fields in a screen. |
| `scan_text_nodes` | Extract all text content and typography properties | `nodeId` (optional), `depth` | Extracting strings for `strings.xml` and typography styles. |
| `search_nodes` | Search nodes by name or text | `query` (string), `nodeTypes` (array) | Locating specific named screens (e.g. "Onboarding_Step_1", "Header"). |
| `get_styles` | Get color, typography, effect, and grid styles | None | Extracting design tokens for Theme/Color system. |
| `get_variable_defs` | Get Figma variable collections & modes | None | Inspecting token variables (Light/Dark themes, Spacing tokens). |
| `export_tokens` | Export design tokens as JSON or CSS | `format` ('json' \| 'css') | Bridging Figma tokens directly into code design system. |
| `get_reactions` | Get prototype interactions (clicks, navigations, delays) | `nodeId` (string) | Extracting UI events, navigation flows, dialog triggers for MVI Intent/Contract. |
| `get_annotations` | Get dev mode annotations and specs | `nodeId` (string) | Reading designer notes, padding rules, or API requirements. |
| `get_screenshot` | Get base64 screenshot of a node | `nodeId` (string) | Visual verification in conversation. |
| `save_screenshots` | Export node screenshots/SVGs directly to disk | `items`: `[{nodeId, outputPath, format, scale}]`, `format` ('PNG'\|'SVG'\|'JPG'\|'PDF'), `scale` | **Intermediate step for asset extraction**. Exports SVG icons to temp files. |
| `convert_svg_to_android_drawable` | Convert SVG files on disk to VectorDrawable XML | `items`: `[{svgPath, outputPath, floatPrecision, fillBlack, tint, xmlTag}]` | **Direct vector generation** to `res/drawable/ic_<name>.xml`. |
| `get_local_components` | Get local component definitions | None | Identifying reusable design components. |
| `get_pages` | List all pages in the Figma file | None | Finding the right page (e.g. "Mobile UI", "Design System"). |
| `get_viewport` | Get current Figma viewport position | None | Checking designer focus area. |
| `get_fonts` | List fonts used in document | None | Checking custom fonts needed in `res/font/`. |

---

## 2. Token-Saving Strategy (CRITICAL)

Figma documents can contain tens of thousands of nodes. **NEVER call `get_document` on an entire document.**

### Recommended Exploration Workflow:
1. **Locate Target**:
   - If user selected nodes in Figma: `call_mcp_tool('figma_mcp_android', 'get_selection', {})`
   - If user specified a screen name: `call_mcp_tool('figma_mcp_android', 'search_nodes', { query: 'ScreenName', nodeTypes: ['FRAME', 'SECTION', 'COMPONENT'] })`
2. **Explore Structure Progressively**:
   - Step 1: `get_design_context` with `depth: 2, detail: 'minimal'` to understand high-level section layout (Header, Content, BottomBar).
   - Step 2: `get_design_context` or `get_node` with `depth: 2, detail: 'full', dedupe_components: true` on specific container nodes.
3. **Extract Content Specifically**:
   - Texts: `scan_text_nodes` on the target frame.
   - Icons: `scan_nodes_by_types` with `nodeTypes: ['COMPONENT', 'INSTANCE', 'VECTOR']`.
   - Interactions: `get_reactions` on clickable buttons/cards.
