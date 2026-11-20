# Drop shadows: the inset rule

Read this before you put `shape_effect<n>Type="dropShadow"` on any view. Each statement
below was checked against the `ShapeView:1.0.2` bytecode (`ShapeEffect.computeInsets`,
`ShapeDrawable.ensureValidRect`, `ShapeDrawableBuilder`) and confirmed on a device.

## What the library actually does

ShapeView **cannot paint outside the view's bounds.** To make room for a shadow, it
reserves an inset on each enabled edge and **shrinks the filled shape inward** by that
inset:

```
left   = max(0, blur + spread - offsetX)
top    = max(0, blur + spread - offsetY)
right  = max(0, blur + spread + offsetX)
bottom = max(0, blur + spread + offsetY)
```

An edge that `shape_effect<n>Edges` leaves out reserves `0`. With several slots, each
edge takes the largest value across the slots.

What follows from that:

- **The visible card is smaller than the view.** Figma's usual card shadow
  (`blur 23, spread 0, x 0, y 11`) reserves `23 / 12 / 23 / 34` dp. That is **46dp less
  width and 46dp less height** than the `layout_width` / `layout_height` you wrote.
- **`shape_effectPadContent` defaults to `true`.** It adds the same insets to the view's
  padding, so children sit inside the shrunk shape. Setting it to `false` does **not**
  give the space back: the shape still shrinks, and children now overflow it.
- **Ripples are inset too.** The foreground ripple is clipped to the shrunk shape.
- **Compiling proves nothing about this.** A fixed `48dp` tab bar with that shadow has
  `48 - 46 = 2dp` left for its text. The build is green and the labels are invisible.
  Only a device screenshot catches it.

## The failure modes this produces

| Symptom on device | Cause |
| :--- | :--- |
| Text in a fixed-height row or pill is fully or partly clipped | Fixed `layout_height` minus the vertical insets is smaller than the content |
| Labels truncate with `…`, units wrap (`mg/` + `dL`) in half-width cards | The horizontal insets (46dp) come off a column that was already narrow |
| A small dot or marker disappears | `size - 2 × blur ≤ stroke`, so nothing is left to fill |
| Cards look farther apart than in Figma | The insets add to the margins you set |
| A shadow is cut flat at one edge | An ancestor clips it (`clipChildren` / `clipToPadding`, or a `PopupWindow`'s bounds) |
| A shadow looks twice as dark | `android:elevation`, or `PopupWindow.elevation`, is stacked on `shape_effect` |

## How to build it correctly

### 1. Turn each Figma effect into tokens once

For each distinct Figma shadow, put the geometry and its insets in `dimen.xml` next to
each other, and put the card style in `styles.xml`. Never repeat the arithmetic in
layouts.

```xml
<dimen name="shadow_card_blur">23dp</dimen>
<dimen name="shadow_card_offset_y">11dp</dimen>
<dimen name="shadow_card_margin_h">-23dp</dimen>
<dimen name="shadow_card_margin_top">-12dp</dimen>
<dimen name="shadow_card_margin_bottom">-34dp</dimen>
<dimen name="shadow_card_inset_v">46dp</dimen>
```

The `margin_*` values are the insets, negated. `inset_v` is `top + bottom`.

### 2. Cancel the insets with negative margins on the card

The view grows outward by exactly the inset, so the visible shape lands where Figma puts
it:

```xml
<style name="Widget.App.Card" parent="">
    <item name="android:layout_marginStart">@dimen/shadow_card_margin_h</item>
    <item name="android:layout_marginEnd">@dimen/shadow_card_margin_h</item>
    <item name="android:layout_marginTop">@dimen/shadow_card_margin_top</item>
    <item name="android:layout_marginBottom">@dimen/shadow_card_margin_bottom</item>
    <item name="shape_radius">@dimen/radius_20</item>
    <item name="shape_solidColor">@color/surface_card</item>
    <item name="shape_effect1Type">dropShadow</item>
    <item name="shape_effect1Color">@color/shadow_card</item>
    <item name="shape_effect1Blur">@dimen/shadow_card_blur</item>
    <item name="shape_effect1OffsetY">@dimen/shadow_card_offset_y</item>
</style>
```

A Figma gap between two cards becomes `gap + negative margin`. For example, a 16dp gap
under a card whose bottom margin is `-34dp` is set as `-18dp`. Give these gaps tokens as
well (`shadow_card_gap_16_bottom`).

Layout rules that negative margins depend on:

- **Use `layout_marginStart` + `layout_marginEnd`.** `MarginLayoutParams` ignores a
  negative `layout_marginHorizontal` / `layout_marginVertical`.
- **Weighted `LinearLayout` children** (`0dp` + `layout_weight`) ignore negative
  horizontal margins. Wrap each card in a `FrameLayout` with `0dp` width and weight `1`,
  and put the card inside with `match_parent` and the negative margins.
- **`ConstraintLayout`** clamps negative margins on constrained edges. Don't rely on them
  there. Wrap the card in a `FrameLayout`, or anchor to a stable sibling.
- **An `<include>` that sets `layout_width` / `layout_height`** replaces the included
  root's `LayoutParams`, so the style's margins are lost. Restate the four margins on the
  `<include>`.

### 3. Give fixed sizes the insets back

Wherever the design gives a fixed height (a tab bar, an input row, a date card), the
view's height is **design height + top inset + bottom inset**. Prefer `minHeight` over
`layout_height` so larger text can still grow it.

```xml
<dimen name="record_datetime_card_height">106dp</dimen>  <!-- 60dp design + 46dp insets -->
```

For narrow columns, check the width the same way: `column width − 46dp − padding` must
still fit the longest label. If it doesn't, the shadow needs one of the patterns in
step 4, not a smaller font.

### 4. Small or one-sided shadows

- **Dots, markers and glows** (a view of a few dp): size the view at
  `design size + 2 × (blur + spread)` and set `shape_effectPadContent="false"`. A 10dp
  marker with a 4dp blur becomes an 18dp view. Grow the container's height to match.
- **Bars and sticky footers** that only cast shadow one way: set
  `shape_effect1Edges="top"` (or `bottom`). The other edges reserve `0`, so the bar keeps
  its full width and stays flush with the screen edges.

### 5. Let the shadow paint, without letting content bleed

- Put `android:clipChildren="false"` and `android:clipToPadding="false"` on the card's
  ancestors, up to the first container that has room around it.
- **Never set them on a `ScrollView` / `NestedScrollView` itself.** Scrolled cards will
  draw over sticky buttons and bottom bars. Set them on the scroll view's inner content
  layout instead, and give that layout padding where the first and last shadows fall.
- **`PopupWindow`**: set `elevation = 0f`, and make the window larger than the anchor by
  the insets (offset by `-inset`). Otherwise the window's bounds clip the shadow.
- **Never combine `android:elevation` with `shape_effect`.** Pick the designer's shadow
  and delete the elevation.

### 6. Runtime

`shapeDrawableBuilder.getShadowInsets()` returns the inset `Rect` in pixels. Use it
anywhere code sizes or positions a shadowed view (popups, custom views), instead of
computing the formula again.

## Checklist for every shadowed view

- [ ] The insets were computed from the Figma effect, and there are tokens for them
- [ ] Negative `Start` / `End` / `Top` / `Bottom` margins cancel the insets, or a wrapper
      or slot pattern handles the parent types that ignore them
- [ ] Every fixed `height` / `minHeight` includes the vertical insets, and each narrow
      column still fits its longest label
- [ ] Ancestors don't clip the shadow, and scroll containers do clip their content
- [ ] No `android:elevation` or `PopupWindow.elevation` on top of `shape_effect`
- [ ] A **device screenshot** of the screen was taken. The compiler can't see any of
      this.
