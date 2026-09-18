---
name: shape-view
description: Use when styling Android XML layouts with ShapeView (com.github.impeterwayne:ShapeView, package com.genesys.shape) - corner radii, borders, fills, gradients, state colours, ripples and drop/inner shadows declared inline as app:shape_* attributes instead of hand-written res/drawable shape, selector and ripple files. Covers the view and layout classes, the full attribute set, the Kotlin builders for runtime changes, and migration of existing bg_*.xml drawables.
---

# ShapeView — the background API for XML layouts

`ShapeView` replaces the `res/drawable/bg_*.xml` file. Anywhere a View needs a rounded
corner, a border, a fill, a gradient, a per-state colour, a ripple or a shadow, that is an
attribute on the view — not a new resource file and not a `GradientDrawable` built in code.

**The rule this skill exists to enforce: do not author a new `<shape>`, `<selector>` or
`<ripple>` drawable.** Reuse an existing one if it already matches; otherwise express it
with `app:shape_*`. A drawable that is a genuine *drawing* — a vector icon, a layer-list,
an animated selector — still belongs in `res/drawable`.

## Setup

```gradle
// settings.gradle — repositories
maven { url 'https://jitpack.io' }

// module build.gradle
implementation 'com.github.impeterwayne:ShapeView:1.0.2'
```

Requires `minSdk` 23+, `compileSdk` 36, Java 17. Check the version catalog before adding
the coordinate — in a project that already ships it, `libs.shape.view` exists and the raw
string is the wrong way to add it.

## The classes

Swap the plain widget for its `Shape` counterpart. Nothing else about the layout changes;
these are ordinary subclasses, so `android:*` attributes, ViewBinding ids and
ConstraintLayout params all behave exactly as before.

| Package | Classes |
| :--- | :--- |
| `com.genesys.shape.layout` | `ShapeLinearLayout`, `ShapeFrameLayout`, `ShapeRelativeLayout`, `ShapeConstraintLayout`, `ShapeRecyclerView`, `ShapeRadioGroup` |
| `com.genesys.shape.view` | `ShapeView`, `ShapeTextView`, `ShapeButton`, `ShapeImageView`, `ShapeEditText`, `ShapeCheckBox`, `ShapeRadioButton` |

`ShapeView` itself is a bare `View` — use it for a divider, a drag handle, a dot, a badge
background, any element that is pure shape with no content.

Every class takes the shape, stroke, ripple and effect attributes. The text attributes
(`shape_text*`) apply only to `ShapeTextView`, `ShapeButton`, `ShapeEditText`,
`ShapeCheckBox`, `ShapeRadioButton`. The compound-button drawable attributes
(`shape_button*Drawable`) apply only to `ShapeCheckBox` and `ShapeRadioButton`.

## The reference material

| Read this | For |
| :--- | :--- |
| [references/attributes.md](./references/attributes.md) | every `shape_*` attribute, grouped, with the enum values spelled out and which classes take which group |
| [references/kotlin-api.md](./references/kotlin-api.md) | the code API — the builder classes, their setters, `ShapeEffect`, the enum constants, and the two rules that cause every bug in it |
| [references/recipes.md](./references/recipes.md) | worked layouts: pill button with states, outlined button, card, drop shadow, gradient CTA, gradient text, selectable chip, sheet header, divider, dashed drop zone, ripple row, ring, rounded remote image |

These references are checked against the published source of `ShapeView:1.0.2`. Read the
attribute or method there before you write it — inventing a plausible-looking `shape_*`
name is the failure mode of this library, and it surfaces as a resource-linking error, not
a Kotlin one.

## The shape of a typical use

```xml
<com.genesys.shape.layout.ShapeLinearLayout
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:orientation="vertical"
    android:paddingHorizontal="@dimen/spacing_16"
    app:shape_radiusInTopStart="@dimen/radius_32"
    app:shape_radiusInTopEnd="@dimen/radius_32"
    app:shape_solidColor="@color/surface_elevated">

    <com.genesys.shape.view.ShapeView
        android:layout_width="48dp"
        android:layout_height="4dp"
        app:shape_radius="100dp"
        app:shape_solidColor="@color/handle_muted" />

</com.genesys.shape.layout.ShapeLinearLayout>
```

Note `shape_radiusInTopStart` / `…TopEnd` rather than `…TopLeft` / `…TopRight` — the
start/end pair is RTL-correct and is what this codebase uses.

## Colour values are resources

`app:shape_solidColor="#1E2025"` compiles, and it is still wrong. Point every colour
attribute at `@color/*` so dark mode and the design system keep working:
`app:shape_solidColor="@color/surface_card"`. Raw hex belongs in `colors.xml` and nowhere
else. The same goes for radii and stroke widths that repeat — `@dimen/radius_12`, not a
`12dp` copied across nine layouts.

## Changing a shape at runtime

Do not swap `background` resources and do not build a `GradientDrawable`. Each view
exposes builders; mutate and commit. Full surface in
[references/kotlin-api.md](./references/kotlin-api.md).

```kotlin
binding.card.shapeDrawableBuilder
    .setSolidColor(ContextCompat.getColor(this, R.color.surface_selected))
    .setRadius(resources.getDimensionPixelSize(R.dimen.radius_12))
    .intoBackground()

binding.label.textColorBuilder
    .setTextColor(ContextCompat.getColor(this, R.color.text_accent))
    .intoTextColor()

binding.checkbox.buttonDrawableBuilder
    .setButtonDrawable(AppCompatResources.getDrawable(this, R.drawable.ic_check_box))
    .intoButtonDrawable()
```

Three things to hold onto:

1. **Builder values are pixels; XML values are dp.** `setRadius(12)` is 12 px, not 12 dp.
   Always come through `resources.getDimensionPixelSize(...)`.
2. **Nothing applies until `.into*()`.** A builder chain without the terminal call is a
   silent no-op. `rippleBuilder` is the exception — it applies as it is set.
3. **Prefer state attributes over runtime toggling.** If the change tracks
   pressed/selected/checked/enabled, declare `shape_solidSelectedColor` in XML and just
   set `isSelected`. Reaching for the builder there is re-implementing the library.

## Migrating an existing `bg_*.xml`

When you touch a layout that still points at a hand-written shape drawable:

1. Read the drawable. Map `<corners>` → `shape_radius*`, `<solid>` → `shape_solidColor`,
   `<stroke>` → `shape_strokeSize`/`shape_strokeColor` (+ `DashSize`/`DashGap`),
   `<gradient>` → the `shape_solidGradient*` family, `<ripple>` → `shape_ripple_*`.
   A `<selector>`'s state items become the `*Pressed`/`*Selected`/`*Checked`/`*Disabled`
   colour attributes on one view.
2. Change the widget to its `Shape` counterpart and move the attributes in.
3. **Grep the drawable name across the whole repo before deleting it.** These files are
   shared constantly; an unused-looking `bg_button_primary.xml` is usually referenced from
   six layouts and a style. If it still has users, leave it and convert only the layout
   you were asked to change.

Migrating drawables nobody asked you to migrate is scope creep. Convert what you touch.

## Checklist

- [ ] No new `<shape>` / `<selector>` / `<ripple>` drawable was created.
- [ ] Every colour attribute points at `@color/*`; repeated radii and strokes at `@dimen/*`.
- [ ] Corners use `TopStart`/`TopEnd`/`BottomStart`/`BottomEnd`, not `Left`/`Right`.
- [ ] Pressed / selected / checked / disabled states are attributes, not code.
- [ ] Runtime changes go through a builder and end in `.intoBackground()` /
      `.intoTextColor()` / `.intoButtonDrawable()`, with px-converted dimensions.
- [ ] A deleted drawable was grepped repo-wide first.
- [ ] The module compiles: `./gradlew :<module>:assembleDebug`. Attribute typos are a
      resource-linking failure, not a Kotlin one, so a `compileDebugKotlin` will not catch
      them.
