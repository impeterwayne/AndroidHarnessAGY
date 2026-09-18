# ShapeView code API

Verified against `com.github.impeterwayne:ShapeView` (`com.genesys.shape`). Use this when
a shape has to change at runtime. When it only changes with pressed / selected / checked /
enabled, declare the state attribute in XML instead — see
[attributes.md](./attributes.md) — and just set `isSelected` / `isChecked` / `isEnabled`.

## Getting a builder

Every `Shape*` class implements one or more accessor interfaces:

| Interface | Getter | Implemented by |
| :--- | :--- | :--- |
| `IGetShapeDrawableBuilder` | `getShapeDrawableBuilder()` | all `Shape*` views and layouts |
| `IGetTextColorBuilder` | `getTextColorBuilder()` | `ShapeTextView`, `ShapeButton`, `ShapeEditText`, `ShapeCheckBox`, `ShapeRadioButton` |
| `IGetButtonDrawableBuilder` | `getButtonDrawableBuilder()` | `ShapeCheckBox`, `ShapeRadioButton` |

From Kotlin these read as properties: `binding.card.shapeDrawableBuilder`,
`binding.label.textColorBuilder`, `binding.check.buttonDrawableBuilder`.

## Two rules that cause every bug in this API

1. **Nothing applies until the terminal call.** `intoBackground()`, `intoTextColor()`,
   `intoButtonDrawable()`. A chain without it is a silent no-op — the most common mistake
   here. `RippleBuilder` is the exception: its setters call `apply()` themselves.
2. **Builder dimensions are pixels. XML dimensions are dp.** `setRadius(12f)` is 12 px.
   Always go through `resources.getDimensionPixelSize(R.dimen.radius_12)`, and colours
   through `ContextCompat.getColor(...)` — these take `@ColorInt`, not `@ColorRes`.

## `ShapeDrawableBuilder`

Every setter returns the builder, so it chains. Getters exist for all of the below;
only the setters are listed.

**Shape** — `setType(@ShapeTypeLimit int)` with `ShapeType.RECTANGLE` / `OVAL` / `LINE` /
`RING`; `setWidth(int)`, `setHeight(int)`.

**Corners** — `setRadius(float)`; `setRadius(topLeft, topRight, bottomLeft, bottomRight)`;
`setRadiusRelative(topStart, topEnd, bottomStart, bottomEnd)` ← prefer this one, it is
RTL-correct. Per corner: `setTopLeftRadius`, `setTopRightRadius`, `setBottomLeftRadius`,
`setBottomRightRadius`.

**Fill** — `setSolidColor(int)` or `setSolidColor(ColorStateList)`, plus
`setSolidPressedColor`, `setSolidCheckedColor`, `setSolidDisabledColor`,
`setSolidFocusedColor`, `setSolidSelectedColor` (all take a nullable `Integer` — pass
`null` to drop the state).

**Fill gradient** — `setSolidGradientColors(start, end)`,
`setSolidGradientColors(start, center, end)`, `setSolidGradientColors(int[])`;
`clearSolidGradientColors()`; `setSolidGradientOrientation(ShapeGradientOrientation)`;
`setSolidGradientType(ShapeGradientType.LINEAR_GRADIENT | RADIAL_GRADIENT | SWEEP_GRADIENT)`;
`setSolidGradientCenterX/Y(float)`; `setSolidGradientRadius(float)`,
`setSolidGradientRadiusSize(float)`, `setSolidGradientRadiusRatio(float)`,
`setSolidGradientRadii(x, y)`; `setSolidRadialAngle(float)`,
`setSolidRadialStartPosition(x, y)`; `setSolidGradientPositions(start, end)` /
`(start, center, end)`; `setLinearGradientPositions(startX, startY, endX, endY)`.

`ShapeGradientOrientation` constants: `LEFT_TO_RIGHT` / `START_TO_END`,
`RIGHT_TO_LEFT` / `END_TO_START`, `TOP_TO_BOTTOM`, `BOTTOM_TO_TOP`,
`TOP_LEFT_TO_BOTTOM_RIGHT` / `TOP_START_TO_BOTTOM_END`,
`TOP_RIGHT_TO_BOTTOM_LEFT` / `TOP_END_TO_BOTTOM_START`,
`BOTTOM_LEFT_TO_TOP_RIGHT` / `BOTTOM_START_TO_TOP_END`,
`BOTTOM_RIGHT_TO_TOP_LEFT` / `BOTTOM_END_TO_TOP_START`. The `START`/`END` spellings flip
under RTL; the `LEFT`/`RIGHT` ones do not.

**Stroke** — `setStrokeSize(int)`, `setStrokeColor(int)` / `(ColorStateList)`,
`setStrokePressedColor`, `setStrokeCheckedColor`, `setStrokeDisabledColor`,
`setStrokeFocusedColor`, `setStrokeSelectedColor`, `setStrokeDashSize(int)`,
`setStrokeDashGap(int)`. The stroke gradient setters mirror the fill ones with `Stroke`
in the name.

**Ring** — `setRingInnerRadiusSize(int)` / `setRingInnerRadiusRatio(float)`,
`setRingThicknessSize(int)` / `setRingThicknessRatio(float)`.

**Effects** — `setEffect(ShapeEffect)`, `addEffect(ShapeEffect)`,
`setEffects(List<ShapeEffect>)`, `clearEffects()`, `setEffectPadContent(boolean)`,
`getShadowInsets(): Rect`.

**Terminal / misc** — `intoBackground()`, `buildBackgroundDrawable(): Drawable`,
`getDrawable()`, `clearBackground()`, `convertShapeDrawable(Drawable)`.

```kotlin
private fun renderSelection(selected: Boolean) {
    binding.card.shapeDrawableBuilder
        .setSolidColor(
            ContextCompat.getColor(
                this,
                if (selected) R.color.surface_selected else R.color.surface_card
            )
        )
        .setStrokeSize(resources.getDimensionPixelSize(R.dimen.stroke_1))
        .setStrokeColor(ContextCompat.getColor(this, R.color.border_subtle))
        .intoBackground()
}
```

That example is the wrong solution, and it is here as the shape to recognise: two
`shape_solid*Color` attributes and `card.isSelected = selected` does the same thing with
no code. Reach for the builder when the value is genuinely dynamic — a colour from the
server, a palette the user picked, a gradient derived from artwork.

## `ShapeEffect`

```kotlin
binding.card.shapeDrawableBuilder
    .setEffect(
        ShapeEffect.dropShadow(
            ContextCompat.getColor(this, R.color.shadow_card),
            resources.getDimensionPixelSize(R.dimen.shadow_blur_16),
            0,
            0,
            resources.getDimensionPixelSize(R.dimen.shadow_dy_4)
        )
    )
    .setEffectPadContent(true)
    .intoBackground()
```

Factories: `ShapeEffect.dropShadow(color, blur, spread, offsetX, offsetY)` and
`ShapeEffect.innerShadow(...)`. Fluent setters: `setType`, `setColor(int)` /
`setColor(ColorStateList)`, `setBlur`, `setSpread`, `setOffset(x, y)`, `setEdges`.
`copy()` gives a detached instance.

Edge flags: `ShapeEffect.EDGE_NONE`, `EDGE_LEFT`, `EDGE_TOP`, `EDGE_RIGHT`, `EDGE_BOTTOM`,
`EDGE_ALL` (the default). Type constants: `ShapeEffectType.DROP_SHADOW`, `INNER_SHADOW`.
Default colour is `0x33000000`.

`addEffect` stacks up to four; slot order is paint order, so the first is the tightest.

## `TextColorBuilder`

`setTextColor(int)`, `setTextPressedColor`, `setTextCheckedColor`, `setTextDisabledColor`,
`setTextFocusedColor`, `setTextSelectedColor`; `setTextGradientColors(start, end)` /
`(start, center, end)` / `(int[])`, `setTextGradientOrientation(int)` with
`TextColorBuilder.GRADIENT_ORIENTATION_HORIZONTAL` / `…_VERTICAL`;
`setTextStrokeColor(int)`, `setTextStrokeSize(int)`; `clearTextGradientColor()`,
`clearTextStrokeColor()`; `buildColorState(): ColorStateList`. Terminal:
`intoTextColor()`.

## `RippleBuilder`

`setRippleEnabled(boolean)`, `setRippleColor(int)`, `setRippleRadius(float)`. These apply
immediately — there is no `into*` call. Reached as `view.rippleBuilder`, or attached with
`shapeDrawableBuilder.setRippleBuilder(...)`.

## `ButtonDrawableBuilder`

`setButtonDrawable(Drawable)`, `setButtonPressedDrawable`, `setButtonCheckedDrawable`,
`setButtonDisabledDrawable`, `setButtonFocusedDrawable`, `setButtonSelectedDrawable`.
Terminal: `intoButtonDrawable()`.
