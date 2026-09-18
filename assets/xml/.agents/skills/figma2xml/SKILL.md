---
name: figma2xml
description: Use when implementing a Figma design as Android XML layouts and Views (no Compose) - turning a figma-spec.md into ConstraintLayout/LinearLayout trees, ShapeView attributes for fills, corners, borders and shadows, Glide for imagery, Epoxy controllers for lists, string and dimension resources, and the Action/SideEffect contract behind the screen. The XML-track counterpart to figma2compose.
---

# Figma to XML layouts

Stage 3 of the Figma pipeline for a View/XML project. The design has already been
inspected (`docs/<feature>/figma-spec.md` + reference PNGs) and its assets are already in
the repo (`docs/<feature>/figma-assets.json`). This skill turns that into layouts and
Kotlin.

**Do not open Figma.** Re-deriving the design here burns the context the implementation
needs, and stage 1 already did it. If the spec is missing a field, take the simplest
reading, say which field you guessed, and continue.

## Required reading

| Read | For |
| :--- | :--- |
| `docs/<feature>/figma-spec.md` | the design. §3 inventory, §4 layout tree, §5 variant matrix, §6 tokens, §7 text, §8 assets, §9 interactions |
| `docs/<feature>/figma-assets.json` | what stage 2 actually produced — apply `renamed[]` and `reused[].requestedAs` before writing any `R.drawable` |
| [figma-design-analyzer/references/layout-mapping-guide.md](../figma-design-analyzer/references/layout-mapping-guide.md) | the auto-layout → XML column |
| [references/layout-mapping-xml.md](./references/layout-mapping-xml.md) | ConstraintLayout translation, sizing, chains, shadows, text, the decisions the shared guide leaves open |
| skill `shape-view` | fills, corners, borders, gradients, state colours, shadows |
| skill `image-loading-glide` | every image that is not a static vector |
| skill `android-xml-views` | base classes, the contract, Epoxy |
| skill `xml-resource-policy` | strings, colours, dimens, text appearances |

## Step 0 — resolve names against the manifest

Before writing a single `R.drawable` reference, find its entry in `exported[]` or
`reused[]` and apply `renamed[]`. A name on the spec's asset list with no manifest entry
means the drawable does not exist: **report the gap, do not write a reference that will
not resolve.** `tokens.conflicts[]` blocks the elements it names; build everything else.

If the manifest is absent, stage 2 did not run. Say so, and verify every name against the
filesystem before using it.

## Step 1 — resources first

1. Static text into `res/values/strings.xml` under the ids §7 proposed, including the
   `cd_*` content descriptions.
2. Confirm every icon exists as `res/drawable/ic_<name>.xml`.
3. Map §6's tokens onto existing `@color` / `@dimen` / `TextAppearance.App.*` entries.
   A token that snaps to an existing resource uses that resource; a genuinely new one is
   declared once in the shared module. **Never a raw hex in a layout.**
4. Build §3's `NEW shared` components once, at the path the inventory names, before the
   screens that consume them.

## Step 2 — the layout tree

Translate §4 top-down. The default container is `ConstraintLayout`; `LinearLayout` earns
its place when the design is a genuine single-axis stack with even spacing, and nesting
past two levels means the ConstraintLayout version was the right call.

The mapping that matters most on this track: **anything in the design with a fill, a
corner radius, a border, a gradient or a shadow becomes a `Shape*` view with `shape_*`
attributes** — not a container plus a new `bg_*.xml` drawable. A rounded card is a
`ShapeConstraintLayout`. A pill button is a `ShapeButton`. A divider or a handle is a
`ShapeView`. Full translation table in
[references/layout-mapping-xml.md](./references/layout-mapping-xml.md).

Every `android:id` is assigned as you go, in the project's convention (`tvTitle`,
`imgThumb`, `btnContinue`, `listDocuments`), because the generated binding field names come
from them and renaming later touches every call site.

## Step 3 — lists

A repeating element in §4 is an Epoxy item model plus a controller, not a
`LinearLayout` the code inflates into. One `item_<name>.xml` per row, one
`@EpoxyModelClass` model over it, one controller that builds the list from state.
Headers, footers, empty states and inline ad slots are models in the same `buildModels`.
See `android-xml-views` → [epoxy-lists.md](../android-xml-views/references/epoxy-lists.md).

## Step 4 — the contract and the screen

For a **new** screen, derive the contract from §9: a trigger becomes an `Action`,
navigation and one-shot feedback become `SideEffect`s, everything visible becomes
`UiState`. Then the Fragment or Activity over `BaseFragment<VB>` / `BaseActivity<VB>`, with
`initViews` / `onClickViews` / `observerData` filled and a total `render(state)`.

For an **existing** screen — the common case — read it first. The `ViewModel`, the
contract, the Epoxy controller, the navigation route and its arguments all stay as they
are. Restyle the layout, update the bind, and leave behaviour alone.

## Step 5 — §5 is a checklist, not a suggestion

The variant matrix enumerates the states the happy path will otherwise hide. For each row:
a `UiState` shape that can express it, and a `render` branch that produces it. Empty,
loading, error, long text, and the selected/disabled variants of every control.

XML has no `@Preview`, so a row is only verified by being driven on a device. That makes
the navigation path you report at the end load-bearing, not a courtesy — floor 4 cannot
reach a state it was not told how to produce.

A row marked `not designed` takes the design system default. Do not invent a treatment for
a state the designer did not draw.

## Zero logic regression

- Never change or remove a ViewModel call, a use case invocation, an analytics trigger or a
  navigation argument to make a layout convenient.
- Never repurpose an existing `UiState` field; add one when the design needs new state.
- If the design removes a control, remove the control — not the action it dispatched — and
  report it.
- Where the design genuinely requires a behaviour change: do the UI work, leave the
  behaviour, and name the conflict in your report.

## Pre-delivery checklist

- [ ] Every `R.drawable` matched to a manifest entry before it was written.
- [ ] No new `<shape>` / `<selector>` / `<ripple>` drawable; fills, corners, borders,
      gradients and shadows are `shape_*` attributes.
- [ ] No raw hex, no literal user-facing text, no loose `textSize`/`fontFamily` pairs.
- [ ] `start`/`end` throughout; no `left`/`right`.
- [ ] Every image and icon has a `contentDescription` from §7's `cd_*` ids, or `@null` if
      decorative.
- [ ] Repeating elements are Epoxy models, not inflated stacks.
- [ ] Every §5 row has a `UiState` shape and a `render` branch.
- [ ] Touch targets are at least 48dp.
- [ ] Layout holds up against long strings and a large font scale.
- [ ] `./gradlew :<module>:assembleDebug` passes — resource errors do not show up in
      `compileDebugKotlin`.
- [ ] Every `R.string`, `R.dimen`, `R.color`, `R.drawable` and binding id introduced was
      grepped.
- [ ] The navigation path to each changed screen is in the report, with the taps that
      reach each §5 state.
