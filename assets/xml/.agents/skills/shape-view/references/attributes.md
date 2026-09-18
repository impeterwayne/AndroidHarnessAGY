# ShapeView attribute reference

Namespace `app:` (`xmlns:app="http://schemas.android.com/apk/res-auto"`). Every attribute
below is declared once and shared across the styleables, so a `shape_solidColor` on a
`ShapeConstraintLayout` means exactly what it means on a `ShapeButton`.

Applies to **all** classes: base shape, corners, fill, fill gradient, stroke, stroke
gradient, ring, line, ripple, effects.
Applies to `ShapeTextView`, `ShapeButton`, `ShapeEditText`, `ShapeCheckBox`,
`ShapeRadioButton`: the text group.
Applies to `ShapeCheckBox`, `ShapeRadioButton`: the button-drawable group.

## Base shape

| Attribute | Format | Notes |
| :--- | :--- | :--- |
| `shape_type` | enum | `rectangle` (default), `oval`, `line`, `ring` |
| `shape_width` | dimension | fixes the drawable's intrinsic width |
| `shape_height` | dimension | fixes the drawable's intrinsic height |

## Corners

`shape_radius` sets all four. The per-corner attributes override it.

`shape_radiusInTopStart`, `shape_radiusInTopEnd`, `shape_radiusInBottomStart`,
`shape_radiusInBottomEnd` — **use these**, they are RTL-correct.

`shape_radiusInTopLeft`, `shape_radiusInTopRight`, `shape_radiusInBottomLeft`,
`shape_radiusInBottomRight` — absolute equivalents; only when the design is genuinely
direction-locked.

A pill is `shape_radius` at any value taller than half the view (e.g. `100dp`).

## Fill

| Attribute | Applies in state |
| :--- | :--- |
| `shape_solidColor` | default |
| `shape_solidPressedColor` | pressed |
| `shape_solidDisabledColor` | `isEnabled = false` |
| `shape_solidFocusedColor` | focused |
| `shape_solidSelectedColor` | `isSelected = true` |
| `shape_solidCheckedColor` | `isChecked = true` |

Declaring these is how a state changes colour. There is no selector file and no code path.

## Fill gradient

`shape_solidGradientStartColor`, `shape_solidGradientCenterColor`,
`shape_solidGradientEndColor` — the stops. Start + end is the common case; add center for
a three-stop.

`shape_solidGradientType` — `linear` (default), `radial`, `sweep`.

`shape_solidGradientOrientation` — `leftToRight` / `startToEnd`, `rightToLeft` /
`endToStart`, `topToBottom`, `bottomToTop`, and the diagonal combinations. The `start`/`end`
variants flip under RTL; the `left`/`right` ones do not.

Stop positions: `shape_solidGradientStartPercent`, `shape_solidGradientCenterPercent`,
`shape_solidGradientEndPercent`.

Explicit endpoints (linear): `shape_solidGradientStartX`, `shape_solidGradientStartY`,
`shape_solidGradientEndX`, `shape_solidGradientEndY`.

Radial / sweep geometry: `shape_solidGradientCenterX`, `shape_solidGradientCenterY`
(float or fraction, default `0.5`), `shape_solidGradientRadius`,
`shape_solidGradientRadiusSize`, `shape_solidGradientRadiusRatio`,
`shape_solidGradientRadiusX`, `shape_solidGradientRadiusY`, `shape_solidRadialAngle`.

## Stroke

`shape_strokeSize`, `shape_strokeColor`, plus the same state set:
`shape_strokePressedColor`, `shape_strokeDisabledColor`, `shape_strokeFocusedColor`,
`shape_strokeSelectedColor`, `shape_strokeCheckedColor`.

Dashes: `shape_strokeDashSize` (dash length), `shape_strokeDashGap`.

Stroke gradients mirror the fill set with `stroke` in place of `solid`:
`shape_strokeGradientStartColor`, `shape_strokeGradientCenterColor`,
`shape_strokeGradientEndColor`, `shape_strokeGradientOrientation`,
`shape_strokeGradientType`, `shape_strokeGradientCenterX/Y`,
`shape_strokeGradientRadiusSize`, `shape_strokeGradientRadiusRatio`,
`shape_strokeGradientRadiusX/Y`, `shape_strokeGradientStartPercent`,
`shape_strokeGradientCenterPercent`, `shape_strokeGradientEndPercent`,
`shape_strokeGradientStartX/Y`, `shape_strokeGradientEndX/Y`, `shape_strokeRadialAngle`.

## Ring (`shape_type="ring"`)

`shape_ringInnerRadiusSize` (absolute) or `shape_ringInnerRadiusRatio` (relative to width),
`shape_ringThicknessSize` or `shape_ringThicknessRatio`.

## Line (`shape_type="line"`)

`shape_lineGravity` — flags: `top`, `bottom`, `left`, `right`, `start`, `end`, `center`.

## Ripple

`shape_ripple_enabled` (boolean), `shape_ripple_color`, `shape_ripple_radius`.

A tappable surface gets a ripple. A ripple on a non-clickable view is invisible and is
noise — give the view `android:clickable="true"` or a click listener, or drop it.

## Effects — shadows

Four independent slots, `shape_effect1*` through `shape_effect4*`. Later slots draw over
earlier ones, so slot 1 is the closest/tightest shadow.

| Attribute (slot *n*) | Format | Notes |
| :--- | :--- | :--- |
| `shape_effect<n>Type` | enum | `dropShadow`, `innerShadow` |
| `shape_effect<n>Color` | color | defaults to `#33000000` once any geometry is set; accepts a selector |
| `shape_effect<n>Blur` | dimension | literal — 8dp of blur fades out over 8dp |
| `shape_effect<n>Spread` | dimension | grows the shadow on every side before blurring; negative shrinks |
| `shape_effect<n>OffsetX` | dimension | positive moves it right |
| `shape_effect<n>OffsetY` | dimension | positive moves it down |
| `shape_effect<n>Edges` | flags | which edges the effect is drawn on |

`shape_effectPadContent` — pads the view's content so a drop shadow does not overlap it.

A Figma drop shadow maps one-to-one: colour → `Color`, blur → `Blur`, spread → `Spread`,
x/y → `OffsetX`/`OffsetY`. Use this rather than `android:elevation`, which gives you the
platform's shadow, not the designer's.

## Text (text-bearing classes only)

State colours: `shape_textColor`, `shape_textPressedColor`, `shape_textDisabledColor`,
`shape_textFocusedColor`, `shape_textSelectedColor`, `shape_textCheckedColor`.

Gradient text: `shape_textStartColor`, `shape_textCenterColor`, `shape_textEndColor`,
`shape_textGradientOrientation`.

Outlined text: `shape_textStrokeColor`, `shape_textStrokeSize`.

`shape_textColor` and `android:textColor` both exist. Use `android:textColor` for a plain
single-state colour; reach for `shape_textColor` when you also need a state or gradient
variant, and then set the whole family there so one place owns it.

## Compound buttons (`ShapeCheckBox`, `ShapeRadioButton`)

`shape_buttonDrawable`, `shape_buttonPressedDrawable`, `shape_buttonCheckedDrawable`,
`shape_buttonDisabledDrawable`, `shape_buttonFocusedDrawable`,
`shape_buttonSelectedDrawable` — a per-state box/tick drawable without a selector file.
