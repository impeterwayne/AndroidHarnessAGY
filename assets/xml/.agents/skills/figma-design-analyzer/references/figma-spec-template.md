# Canonical `figma-spec.md` Template

This file is the **only** definition of the spec's shape. `figma-analyzer`,
`figma-asset-extractor`, `figma-xml-developer`, and `verifier` all read a spec written
to this template — so a section renamed here is a contract change for four agents, and a
section invented anywhere else is a section nobody downstream will look for.

Write it to `docs/<feature>/figma-spec.md`. Reference screenshots go beside it in
`docs/<feature>/figma/`.

## Rules that make it machine-readable

- **Never rename a heading or a table column.** Downstream agents `grep_search` for both.
- **Every table keeps its columns even when a cell is empty** — write `—`, not a dropped
  column.
- **Node ids are observed, never constructed.** An id you did not see in an MCP response
  does not go in the spec.
- **Values are tokens where a token exists, dp/sp where one does not.** A raw hex outside
  §6 is a defect.
- Anything you could not determine goes in §9 as an open question. A guessed value that
  reads like an observed one is the single most expensive failure in this pipeline.

---

# Figma Design Spec: <Feature / Flow Name>

## 1. Provenance

| Field | Value |
|---|---|
| Figma file key | `<key>` |
| Analysed at | `<YYYY-MM-DD>` |
| Frames covered | `<n>` |
| Reference images | `docs/<feature>/figma/` |
| Spec status | `DRAFT` \| `CONFIRMED` |

**MCP calls made** — one line each, so the next analyst knows what was already paid for
and what was never looked at:

```
get_design_context depth=2 detail=minimal   -> skeleton of 145:220
get_design_context depth=3 detail=compact   -> 145:230 (content column)
scan_text_nodes    145:220 depth=4          -> 18 text nodes
get_reactions      145:244                  -> 2 reactions
```

**Not inspected** — name every branch you deliberately skipped and why. Silence here reads
as coverage.

## 2. Screens

One row per frame. `Target file` is where stage 3 will write; leave it `NEW` when no
screen exists yet, and give the existing path when there is one — that single column is
what turns a rewrite into an edit.

| Screen | Node ID | Size (dp) | Reference image | Target file | Mode |
|---|---|---|---|---|---|
| Home | `145:220` | `360x800` | `figma/ref-home.png` | `feature/home/.../HomeScreen.kt` | `RESTYLE` |
| Device picker | `145:512` | `360x520` | `figma/ref-device-picker.png` | `NEW` | `NEW` |

`Mode` is `RESTYLE` (screen exists, visual change only), `NEW`, or `DIFF` (report-only).

## 3. Component inventory

**Fill this in before §5, and for a single-frame job say so explicitly rather than deleting
the section.** A component that appears on three frames must be built once; discovering
that during stage 3 means it has already been built three times.

| Component | Figma node(s) | Appears on | Existing match | Decision |
|---|---|---|---|---|
| Device card | `145:300`, `145:520` | Home, Device picker | `core/ui/res/layout/view_panel.xml` | `REUSE view_panel` |
| Cast CTA | `145:244` | Home | `Widget.App.Button.Primary` | `REUSE` |
| Signal meter | `145:318` | Home, Detail | — | `NEW shared -> core/ui/custom_view/SignalMeterView.kt` |

`Decision` is one of `REUSE <name>`, `REUSE <name> + param`, `NEW shared -> <path>`, or
`NEW local`. `NEW local` needs a reason the existing component could not be parameterised.

The most valuable row in this table is a `REUSE` — it deletes work in stages 2 and 3.

## 4. Layout tree

Per screen, the Auto-Layout tree **already mapped to Android views**. Raw Figma jargon
(`layoutMode`, `counterAxisAlignItems`, `primaryAxisSizingMode`) does not belong here —
translating it is stage 1's job, not the implementer's.

```
activity_home.xml  ShapeConstraintLayout  match_parent x match_parent, @color/bg_base
├─ topBar     LinearLayout(horizontal)  match_parent x 56dp,
│             paddingHorizontal @dimen/spacing_16, gravity center_vertical
│  ├─ ivBack        24dp, srcCompat ic_back, tint @color/text_primary
│  └─ tvTitle       0dp weight 1, textAppearance TextAppearance.App.TitleLarge
├─ rvContent  EpoxyRecyclerView  0dp x 0dp (constrained top and bottom),
│             paddingHorizontal @dimen/spacing_16, item gap @dimen/spacing_8
│  └─ items         DeviceItemModel over item_device.xml (see §3)
└─ bottomBar  ShapeLinearLayout(vertical)  match_parent x wrap_content
   └─ btnCta        ShapeButton, match_parent x 52dp,
                    shape_radius @dimen/radius_pill, shape_solidColor @color/brand_primary
```

Every node carries: the view or layout class — the `Shape*` variant wherever the node has
a fill, radius, border, gradient or shadow — the `android:id` the binding will expose,
sizing (`match_parent`, `wrap_content`, `0dp` plus constraints or weight, or a fixed dp),
gravity and alignment, and padding and gaps as `@dimen` names. Where a measured value has
no resource, write the dp and add a §6 gap row.

## 5. Variant & state matrix

**The section stage 3 builds `render` branches from, and floor 4 walks on the device.**
One row per state the design actually defines — a state not listed here is a state that
will not be implemented and will not be checked. XML has no previews, so the last column
is the route that produces the state rather than a preview flag. An empty cell there means
the row cannot be verified.

| Screen | State | Figma variant node | What differs | How to reach it on device |
|---|---|---|---|---|
| Home | Default | `145:220` | — | launch |
| Home | Loading | `145:601` | list replaced by 3 shimmer rows | launch, first frame before the scan returns |
| Home | Empty | `145:640` | illustration + `home_empty_title` | launch with no paired devices |
| Home | Error | — | not designed — see §9 | — |
| Home | Dark | `145:220` mode `Dark` | `values-night` colours only, layout identical | system dark mode on |

Interactive states go in the same table, one row each: `Pressed`, `Disabled`, `Focused`,
`Selected`. When Figma defines none for a component, write `not designed` rather than
inventing one — the design system default then applies, and that is a decision worth
being visible.

## 6. Token map

**Used** — values that already have a home. Stage 2 does nothing with these.

| Role in UI | Figma value | Resource |
|---|---|---|
| Screen background | `#0E0F13` | `@color/bg_base` |
| Card corner | `12` | `@dimen/radius_12`, applied as `app:shape_radius` |
| Gutter | `16` | `@dimen/spacing_16` |

**Gaps** — values with no token. Stage 2 owns this table and nothing else in §6. Fill
`Nearest existing` honestly; it is the input to the snap decision, and an empty cell reads
as "no near token exists".

| Role in UI | Figma value | Nearest existing | Δ | Proposed |
|---|---|---|---|---|
| Card inner gap | `15dp` | `@dimen/spacing_16 = 16dp` | `1dp` | snap to `@dimen/spacing_16` |
| Accent stroke | `#3DDC97` | — | — | add `@color/accent_success` |

## 7. Text

**Static** — destined for `res/values/strings.xml`.

| String | Proposed id | Screen | Text appearance | Colour |
|---|---|---|---|---|
| `Nearby devices` | `home_nearby_title` | Home | `TextAppearance.App.TitleMedium` | `@color/text_primary` |

**Dynamic** — fed from state.

| Sample | State field | Screen | Text appearance | Colour |
|---|---|---|---|---|
| `Living Room TV` | `uiState.devices[].name` | Home | `TextAppearance.App.BodyLarge` | `@color/text_primary` |

Content descriptions for every icon and image go in the static table with a `cd_` prefix.
An icon with no `contentDescription` row is an accessibility defect stage 3 will inherit.

## 8. Assets

**This table is a contract with stage 2.** The `Target path` column is the exact path
stage 2 writes and stage 3 references — not a suggestion. Stage 2 may reject a name, but
it must then say so in its manifest rather than quietly choosing another.

**Vector icons** — the outer container node, never a child `VECTOR` path.

| Name | Node ID | Container size | Target path | Tint at call site |
|---|---|---|---|---|
| `ic_back` | `145:222` | `24x24` | `core/ui/src/main/res/drawable/ic_back.xml` | `app:tint="@color/text_primary"` |

**Raster and remote**

| Name | Node ID | Kind | Render path |
|---|---|---|---|
| `img_empty_devices` | `145:643` | bundled illustration | `app:srcCompat` |
| device thumbnail | — | remote URL | `GlideImageView`, via `app:glideSrc` |

**Already in the repo** — what you found with `grep_search` and stage 2 must therefore not
export. This row is a cost saving; do not leave it empty out of haste.

| Name | Existing path |
|---|---|
| `ic_close` | `core/ui/src/main/res/drawable/ic_close.xml` |

## 9. Interaction map

From `get_reactions`. Phrased as user action and system response, because this table is
the `Action` / `SideEffect` contract.

| Source node | Trigger | Response | Action | Side effect |
|---|---|---|---|---|
| `145:222` | `ON_CLICK` | back to previous screen | `BackClicked` | `NavigateBack` |
| `145:300` | `ON_CLICK` | open device detail | `DeviceClicked(id)` | `NavigateToDetail(id)` |
| `145:244` | `ON_CLICK` | start casting, CTA shows spinner | `CastClicked` | — (state only) |

A response that changes state only has no side effect — write `—`, do not invent a
navigation.

## 10. Annotations and open questions

Designer notes from `get_annotations` first; they override every inference above.

Then the open questions, each one actionable:

- `Error` state is not designed. Assumed: inline `AppErrorPanel`, matching Settings.
- Card gap measures `15dp`, off the 4dp grid. Snapping to `spacing.md` per §6 — confirm.
- `get_reactions` returned nothing for the filter chip row. Behaviour unknown.

An empty §10 on a real screen is a claim that the design was unambiguous. It rarely was.
