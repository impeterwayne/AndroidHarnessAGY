---
trigger: always_on
---

# Figma Trigger Rule

When a message carries a **Figma URL** (`https://www.figma.com/design/...`, `/file/...`)
or a **node-id** / screen name, the Figma pipeline runs. Do not skip to writing code, and
do not guess at a design you have not inspected.

## Route, do not improvise

| Request | Entry point |
| :--- | :--- |
| Spec, analysis, or a visual diff | `figma-analyzer` → skill `figma-design-analyzer` |
| Icons, images, or design tokens only | `figma-asset-extractor` |
| Build or restyle a screen | the full pipeline, sequenced by `orchestrator` |

The stages, their ordering, and the re-dispatch rules live in **`.agents/agents/orchestrator.md`
→ The Figma pipeline**. The MCP call sequence and budget live in the
`figma-design-analyzer` skill. Neither is restated here — one copy of each, or they drift.

## The two things that are always true

1. **Convert the node-id.** URLs encode the colon as `%3A` or `-`. `node-id=123-456` is
   `123:456` for every MCP call.
2. **Never call `get_document`.** A whole Figma file exhausts the context window and ends
   the task. Bounded `get_design_context` only.

## The artefacts

Each stage hands the next a file, and each file has one owner:

- `docs/<feature>/figma-spec.md` — stage 1. Shape fixed by
  `.agents/skills/figma-design-analyzer/references/figma-spec-template.md`.
- `docs/<feature>/figma/ref-*.png` — stage 1. The reference images floor 4 compares against.
- `docs/<feature>/figma-assets.json` — stage 2. Schema in
  `.agents/skills/figma-asset-extractor/references/asset-manifest.md`.

Implementation follows `.agents/rules/xml.md`: `ConstraintLayout` trees, ShapeView
`app:shape_*` attributes for every fill, corner, border, gradient and shadow,
`@string`/`@color`/`@dimen` resources, `TextAppearance.App.*`, Glide imagery, Epoxy lists,
and existing ViewModel and navigation contracts left intact.

## Reading a Compose-worded stage

Stages 1, 2 and 4 are written in Compose vocabulary, because the spec template and the
analyzer are shared with the Compose harness. They do the same work against different
targets here. Translate as you read, and never send a stage back for using the wrong word:

| Where they say | On this project read |
| :--- | :--- |
| a `core/designsystem` component | a shared layout, custom view or `Widget.App.*` style in `core/ui` |
| `AppTheme.colorScheme` / `.spacing` / `.shapes` | `@color/*` / `@dimen/*` / ShapeView `shape_radius*` |
| `AppTheme.typography` | `TextAppearance.App.*` in `typography.xml` |
| `stringResource(...)` | `@string/…` in the layout, `getString(...)` in Kotlin |
| Landscapist `GlideImage` | `GlideImageView` or the `loadImage` extension |
| a `@Composable`, a `Row` / `Column` / `Box` | a layout file, a `LinearLayout` or `ConstraintLayout` subtree |
| a `LazyColumn` | an `EpoxyRecyclerView` and its controller |
| a `@Preview` per variant row | a device-driven check per variant row. **XML has no previews**, so the navigation path stage 3 reports is the only thing floor 4 can run on |
| raw hex allowed in `:core:designsystem` | raw hex allowed in `colors.xml`, and nowhere else |

Vector icons land in `res/drawable/ic_*.xml` on both harnesses — stage 2 needs no
translation there.
