# Figma to XML — the translation table

Companion to
[figma-design-analyzer/references/layout-mapping-guide.md](../../figma-design-analyzer/references/layout-mapping-guide.md),
which gives the Figma-property column. This file covers what that guide leaves open: which
container to pick, how sizing maps, and how the parts of a design that would otherwise
become `res/drawable` files become ShapeView attributes instead.

## Picking the container

| The frame | Use |
| :--- | :--- |
| anything with more than three children, or any non-trivial alignment | `ConstraintLayout` |
| a genuine single-axis stack, even spacing, no cross-axis alignment work | `LinearLayout` |
| overlays — a badge on an avatar, a scrim, a floating button over content | `FrameLayout`, or `ConstraintLayout` |
| a scrolling screen | `NestedScrollView` wrapping one `ConstraintLayout` |
| a repeating list | `EpoxyRecyclerView` + a controller |
| a horizontal strip inside a vertical list | Epoxy `carousel`, not a nested `RecyclerView` |

Default to `ConstraintLayout`. Nested `LinearLayout`s past two levels is the signal you
chose wrong — flatten it.

Whenever that container also has a fill, a corner radius, a border or a shadow, it is the
`Shape*` variant of it: `ShapeConstraintLayout`, `ShapeLinearLayout`, `ShapeFrameLayout`,
`ShapeRelativeLayout`.

## Auto-layout

| Figma | XML |
| :--- | :--- |
| `layoutMode: VERTICAL` | `LinearLayout` `android:orientation="vertical"`, or a vertical constraint chain |
| `layoutMode: HORIZONTAL` | `android:orientation="horizontal"`, or a horizontal chain |
| `layoutMode: NONE` | `FrameLayout`, or constraints to parent edges |
| `itemSpacing: N` | `android:layout_marginTop/Start="Ndp"` on each child but the first. In a chain, the margin on the constrained side |
| `paddingX/Y` | `android:paddingHorizontal` / `paddingVertical` when symmetric, `paddingStart`/`Top`/`End`/`Bottom` when not |
| `primaryAxisAlignItems: SPACE_BETWEEN` | a `packed`→`spread_inside` chain, or `layout_weight` on the flexible child |
| `primaryAxisAlignItems: CENTER` | `android:gravity="center"`, or `chainStyle="packed"` with both ends constrained |
| `counterAxisAlignItems: CENTER` | `android:layout_gravity="center_vertical"`, or constrain both cross-axis edges |

## Sizing

| Figma resizing | XML |
| :--- | :--- |
| `FIXED` | the literal `dp` |
| `HUG` contents | `wrap_content` |
| `FILL` container | `match_parent` in a `LinearLayout`; `0dp` with both opposing constraints set in a `ConstraintLayout` |
| `FILL` with siblings sharing the axis | `0dp` + `layout_weight` (Linear), or a chain with `layout_constraintHorizontal_weight` |
| fixed aspect ratio | `app:layout_constraintDimensionRatio="16:9"` with one dimension `0dp` |
| min/max width | `android:minWidth` / `app:layout_constraintWidth_max` |

`0dp` in a `ConstraintLayout` means "match constraints". A child with `0dp` and only one
constraint on that axis collapses to nothing — this is the single most common broken
layout, and it looks fine in the XML.

## Fills, corners, borders, gradients, shadows

All of these are `shape_*` attributes on a `Shape*` view. **None of them is a new
`res/drawable` file.** See skill `shape-view` for the attribute set and the recipes.

| Figma | XML |
| :--- | :--- |
| solid fill | `app:shape_solidColor="@color/…"` |
| corner radius (uniform) | `app:shape_radius="@dimen/radius_N"` |
| corner radius (per corner) | `shape_radiusInTopStart` / `TopEnd` / `BottomStart` / `BottomEnd` |
| stroke | `app:shape_strokeSize` + `app:shape_strokeColor` |
| dashed stroke | `+ shape_strokeDashSize` / `shape_strokeDashGap` |
| linear gradient fill | `shape_solidGradientStartColor` / `EndColor` / `Orientation` |
| radial or angular gradient | `shape_solidGradientType="radial"` / `"sweep"` + the centre and radius attributes |
| gradient on text | `shape_textStartColor` / `shape_textEndColor` / `shape_textGradientOrientation` |
| drop shadow | `shape_effect1Type="dropShadow"` + `Color` / `Blur` / `Spread` / `OffsetX` / `OffsetY`; add `shape_effectPadContent="true"` |
| inner shadow | `shape_effect1Type="innerShadow"`, same geometry |
| two stacked shadows | `shape_effect1*` and `shape_effect2*` |
| pressed / selected / disabled fill | `shape_solidPressedColor` / `SelectedColor` / `DisabledColor` |
| pressed / selected text colour | `shape_textPressedColor` / `shape_textSelectedColor` |
| ripple on tap | `shape_ripple_enabled="true"` + `shape_ripple_color` |

A Figma shadow maps one-to-one onto the effect attributes. `android:elevation` gives the
platform's shadow, which is not the one in the mock — use it only where the design is
explicitly Material elevation.

## Text

| Figma | XML |
| :--- | :--- |
| a text style from the library | `android:textAppearance="@style/TextAppearance.App.<Name>"` |
| a one-off size/weight the library does not have | flag it as a token gap; do not inline the values |
| `letterSpacing` | `android:letterSpacing` (em, not sp — Figma's px value ÷ font size) |
| line height | `android:lineHeight` on API 28+, or `lineSpacingExtra` where the project supports older |
| max lines + ellipsis | `android:maxLines` + `android:ellipsize="end"` |
| truncation in the middle | `android:ellipsize="middle"` |
| alignment | `android:textAlignment="viewStart"` / `center` / `viewEnd` — not `gravity` for text alignment |
| auto-shrink to fit | `app:autoSizeTextType="uniform"` with min/max/step |

The colour goes in `android:textColor` for a plain single state; move it to the
`shape_text*` family as soon as a second state exists, so one place owns it.

## Images and icons

| Figma | XML |
| :--- | :--- |
| a flat 1–2 colour icon | `app:srcCompat="@drawable/ic_<name>"`, tinted with `app:tint` |
| an icon that is also a tap target | wrap or size to at least 48dp; the glyph stays 24dp |
| raster artwork shipped with the app | `app:srcCompat="@drawable/img_<name>"` |
| a remote or dynamic image | `com.genesys.glideimageview.GlideImageView` with `app:glideSrc`, `app:glidePlaceholder` / `glideError` — see `image-loading-glide` |
| an image with a corner radius | `GlideImageView` with `app:glideRadius` (or `ShapeImageView` frame + `GlideImageView`) |
| a circular avatar | `GlideImageView` with `app:glideCircle="true"` |
| `scaleMode: FILL` | `android:scaleType="centerCrop"` |
| `scaleMode: FIT` | `android:scaleType="fitCenter"` |

## Interaction

| Figma | XML / Kotlin |
| :--- | :--- |
| a tap | a click listener in `onClickViews()` that dispatches an `Action` |
| a tap that navigates | the action → ViewModel → a `SideEffect` the view performs |
| a selected/unselected variant pair | `isSelected` on a `Shape*` view with the state colours in XML |
| a checkbox or toggle | `ShapeCheckBox` with `shape_buttonCheckedDrawable`, or a `SwitchMaterial` if the project uses Material |
| a sheet or dialog | shown from a `SideEffect`, never from the listener directly |
| a scroll-triggered change | a scroll listener that dispatches an action; the ViewModel decides |

## Things the design will ask for that XML does not do directly

- **Blur** — `RenderEffect` on API 31+, or the project's existing `BlurView`. Check the
  dependency list before adding a library.
- **Layered gradients on one element** — a `Shape*` view with one gradient plus an overlay
  `View` on top. Two gradients on one drawable is not expressible.
- **Arbitrary shapes** — a vector drawable, not a `shape_*` attribute.
- **Auto-layout wrapping** — `FlexboxLayout`, or fixed rows if only two cases exist. Do
  not simulate it with a `RecyclerView` and a `FlexboxLayoutManager` unless the content is
  genuinely dynamic.

When the design needs one of these, say so in the report with the element named. A layout
that silently approximates the design is worse than one that flags the gap.
