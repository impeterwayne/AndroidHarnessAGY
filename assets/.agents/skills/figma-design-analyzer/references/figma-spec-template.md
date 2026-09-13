# Canonical `figma-spec.md` Template

This file is the **only** definition of the spec's shape. `figma-analyzer`,
`figma-asset-extractor`, `figma-compose-developer`, and `verifier` all read a spec written
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
| Device card | `145:300`, `145:520` | Home, Device picker | `core/designsystem/AppPanel` | `REUSE AppPanel` |
| Cast CTA | `145:244` | Home | `AppPrimaryButton` | `REUSE` |
| Signal meter | `145:318` | Home, Detail | — | `NEW shared -> feature/home/component/` |

`Decision` is one of `REUSE <name>`, `REUSE <name> + param`, `NEW shared -> <path>`, or
`NEW local`. `NEW local` needs a reason the existing component could not be parameterised.

The most valuable row in this table is a `REUSE` — it deletes work in stages 2 and 3.

## 4. Layout tree

Per screen, the Auto-Layout tree **already mapped to Compose**. Raw Figma jargon
(`layoutMode`, `counterAxisAlignItems`, `primaryAxisSizingMode`) does not belong here —
translating it is stage 1's job, not the implementer's.

```
HomeScreen  Scaffold
├─ topBar    Row   fillMaxWidth, height 56.dp, padding(horizontal = spacing.md)
│            verticalAlignment = CenterVertically, spacedBy(spacing.sm)
│  ├─ ic_back        24.dp, tint colorScheme.colorText
│  └─ title          AppText, typography.titleLarge, weight(1f)
├─ content   LazyColumn  fillMaxSize, contentPadding(spacing.md), spacedBy(spacing.sm)
│  └─ items          DeviceCard (see §3)
└─ bottomBar Column fillMaxWidth, padding(spacing.md)
   └─ cta            AppPrimaryButton, fillMaxWidth, height 52.dp
```

Every node carries: the Compose container or component, sizing (`fillMaxWidth`,
`weight(1f)`, fixed dp, or hug), arrangement and alignment, and padding/gaps as
`AppTheme.spacing` names. Where a measured value has no token, write the dp and add a §6
gap row.

## 5. Variant & state matrix

**The section stage 3 builds previews from.** One row per state the design actually
defines — a state not listed here is a state that will not be implemented and will not be
previewed.

| Screen | State | Figma variant node | What differs | Preview required |
|---|---|---|---|---|
| Home | Default | `145:220` | — | yes |
| Home | Loading | `145:601` | list replaced by 3 shimmer rows | yes |
| Home | Empty | `145:640` | illustration + `home_empty_title` | yes |
| Home | Error | — | not designed — see §9 | no |
| Home | Dark | `145:220` mode `Dark` | `colorScheme` only, layout identical | yes |

Interactive states go in the same table, one row each: `Pressed`, `Disabled`, `Focused`,
`Selected`. When Figma defines none for a component, write `not designed` rather than
inventing one — the design system default then applies, and that is a decision worth
being visible.

## 6. Token map

**Used** — values that already have a home. Stage 2 does nothing with these.

| Role in UI | Figma value | `AppTheme` token |
|---|---|---|
| Screen background | `#0E0F13` | `colorScheme.colorBgBase` |
| Card corner | `12` | `shapes.shape12` |
| Gutter | `16` | `spacing.md` |

**Gaps** — values with no token. Stage 2 owns this table and nothing else in §6. Fill
`Nearest existing` honestly; it is the input to the snap decision, and an empty cell reads
as "no near token exists".

| Role in UI | Figma value | Nearest existing | Δ | Proposed |
|---|---|---|---|---|
| Card inner gap | `15dp` | `spacing.md = 16dp` | `1dp` | snap to `spacing.md` |
| Accent stroke | `#3DDC97` | — | — | add `colorScheme.colorAccentSuccess` |

## 7. Text

**Static** — destined for `res/values/strings.xml`.

| String | Proposed id | Screen | Typography | Colour token |
|---|---|---|---|---|
| `Nearby devices` | `home_nearby_title` | Home | `typography.titleMedium` | `colorText` |

**Dynamic** — fed from state.

| Sample | State field | Screen | Typography | Colour token |
|---|---|---|---|---|
| `Living Room TV` | `uiState.devices[].name` | Home | `typography.bodyLarge` | `colorText` |

Content descriptions for every icon and image go in the static table with a `cd_` prefix.
An icon with no `contentDescription` row is an accessibility defect stage 3 will inherit.

## 8. Assets

**This table is a contract with stage 2.** The `Target path` column is the exact path
stage 2 writes and stage 3 references — not a suggestion. Stage 2 may reject a name, but
it must then say so in its manifest rather than quietly choosing another.

**Vector icons** — the outer container node, never a child `VECTOR` path.

| Name | Node ID | Container size | Target path | Tint at call site |
|---|---|---|---|---|
| `ic_back` | `145:222` | `24x24` | `core/designsystem/src/main/res/drawable/ic_back.xml` | `colorScheme.colorText` |

**Raster and remote**

| Name | Node ID | Kind | Render path |
|---|---|---|---|
| `img_empty_devices` | `145:643` | bundled illustration | `painterResource` |
| device thumbnail | — | remote URL | Landscapist `GlideImage` |

**Already in the repo** — what you found with `grep_search` and stage 2 must therefore not
export. This row is a cost saving; do not leave it empty out of haste.

| Name | Existing path |
|---|---|
| `ic_close` | `core/designsystem/src/main/res/drawable/ic_close.xml` |

## 9. Interaction map

From `get_reactions`. Phrased as user action and system response, because this table is
the MVI contract.

| Source node | Trigger | Response | Event | Side effect |
|---|---|---|---|---|
| `145:222` | `ON_CLICK` | back to previous screen | `OnBackClicked` | `NavigateBack` |
| `145:300` | `ON_CLICK` | open device detail | `OnDeviceClicked(id)` | `NavigateToDetail(id)` |
| `145:244` | `ON_CLICK` | start casting, CTA shows spinner | `OnCastClicked` | — (state only) |

A response that changes state only has no side effect — write `—`, do not invent a
navigation.

## 10. Annotations and open questions

Designer notes from `get_annotations` first; they override every inference above.

Then the open questions, each one actionable:

- `Error` state is not designed. Assumed: inline `AppErrorPanel`, matching Settings.
- Card gap measures `15dp`, off the 4dp grid. Snapping to `spacing.md` per §6 — confirm.
- `get_reactions` returned nothing for the filter chip row. Behaviour unknown.

An empty §10 on a real screen is a claim that the design was unambiguous. It rarely was.
