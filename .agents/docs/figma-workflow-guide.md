# Figma MCP Integration: Jetpack Compose UI Workflow Guide for Antigravity CLI

This guide outlines the streamlined **Skills** and **Agents** ecosystem configured in `.agents/` optimized for **implementing, updating, and maintaining Android screens** from Figma designs in Jetpack Compose within Antigravity CLI.

---

## 1. Directory Structure

```text
.agents/
├── agents/                       # Custom Agent & Subagent definitions (flat <name>.md)
│   ├── figma-ui-specialist.md
│   ├── figma-analyzer.md
│   ├── figma-asset-extractor.md
│   ├── figma-compose-developer.md
│   └── srs-generator.md
├── skills/                       # Procedural skills — also what `/<name>` resolves to
│   ├── figma-design-analyzer/
│   ├── figma-asset-extractor/
│   ├── figma-to-compose/
│   ├── android-resource-policy/
│   ├── android-code-indexer/
│   └── code-review/
├── rules/
│   ├── figma-workflow-trigger.md
│   └── lean.md
├── hooks.json                    # Lifecycle hook profiles
├── hooks/                        # Hook handler scripts
├── scripts/                      # CLIs the agent calls (loop.py)
└── docs/
    ├── architecture.md
    └── figma-workflow-guide.md
```

---

## 2. Custom Agents in `.agents/agents/`

| Agent Name | Definition File | Primary Role |
|---|---|---|
| **`figma-ui-specialist`** | [`.agents/agents/figma-ui-specialist.md`](../agents/figma-ui-specialist.md) | **Full-Stack UI Specialist**: End-to-end screen development (inspects Figma, extracts VectorDrawables, updates `AppTheme` tokens, and implements Jetpack Compose layouts with `GlideImage`). |
| **`figma-analyzer`** | [`.agents/agents/figma-analyzer.md`](../agents/figma-analyzer.md) | **Design Diff Specialist**: Inspects Figma frames, extracts layout specs/typography/assets, and compares against existing code. |
| **`figma-asset-extractor`** | [`.agents/agents/figma-asset-extractor.md`](../agents/figma-asset-extractor.md) | **Asset Pipeline Engineer**: Batch exports SVGs to `res/drawable/ic_*.xml`, exports raster artwork, and bridges tokens to `:core:designsystem`. |
| **`figma-compose-developer`** | [`.agents/agents/figma-compose-developer.md`](../agents/figma-compose-developer.md) | **Compose Specialist**: Composable implementation and updates preserving `ViewModel`, Orbit MVI contracts, and `UiState`. |

---

## 3. Specialized Skills in `.agents/skills/`

| Skill | Location | Role in UI Workflow |
|---|---|---|
| **`figma-design-analyzer`** | [`.agents/skills/figma-design-analyzer/`](../skills/figma-design-analyzer/SKILL.md) | Bounded tree traversal (`get_design_context`), Auto-Layout spacing, typography, asset classification, and prototype reaction analysis. |
| **`figma-asset-extractor`** | [`.agents/skills/figma-asset-extractor/`](../skills/figma-asset-extractor/SKILL.md) | Batch converts SVG icons to `res/drawable/ic_*.xml`, exports raster graphics, and updates `:core:designsystem` tokens. |
| **`figma-to-compose`** | [`.agents/skills/figma-to-compose/`](../skills/figma-to-compose/SKILL.md) | Translates Figma design specs into production-ready Jetpack Compose UI code adhering to Clean Architecture + Orbit MVI. |
| **`android-resource-policy`** | [`.agents/skills/android-resource-policy/`](../skills/android-resource-policy/SKILL.md) | Enforces asset naming, reuse, `AppTheme` token adoption, and avoids hardcoded strings/colors. |
| **`android-code-indexer`** | [`.agents/skills/android-code-indexer/`](../skills/android-code-indexer/SKILL.md) | Rapidly locates existing screen files, Composables, and ViewModels across modules. |

---

## 4. Technical References

- [Figma to Jetpack Compose Layout Mapping Guide](../skills/figma-design-analyzer/references/layout-mapping-guide.md)
- [Figma MCP Tools Reference & Best Practices](../skills/figma-design-analyzer/references/figma-mcp-tools.md)
- [VectorDrawable Extraction Rules](../skills/figma-asset-extractor/references/vector-drawable-rules.md)
- [Deriving MVI Contract from Figma Design](../skills/figma-to-compose/references/mvi-contract-from-figma.md)
