# ShapeView recipes

Each recipe is the ShapeView answer to a `res/drawable` file you would otherwise write.
Colours and dimensions are shown as resource references because that is the rule — swap in
this project's actual token names.

## Filled pill button with pressed and disabled states

Replaces: `bg_button_primary.xml` (`<selector>` of three `<shape>`s).

```xml
<com.genesys.shape.view.ShapeButton
    android:id="@+id/btnContinue"
    android:layout_width="match_parent"
    android:layout_height="52dp"
    android:text="@string/action_continue"
    android:textAppearance="@style/TextAppearance.App.LabelLarge"
    app:shape_radius="@dimen/radius_pill"
    app:shape_solidColor="@color/brand_primary"
    app:shape_solidPressedColor="@color/brand_primary_pressed"
    app:shape_solidDisabledColor="@color/brand_primary_disabled"
    app:shape_textColor="@color/on_brand"
    app:shape_textDisabledColor="@color/on_brand_disabled" />
```

## Outlined secondary button

Replaces: `bg_button_outline.xml`.

```xml
<com.genesys.shape.view.ShapeButton
    android:layout_width="match_parent"
    android:layout_height="52dp"
    android:text="@string/action_cancel"
    app:shape_radius="@dimen/radius_pill"
    app:shape_solidColor="@android:color/transparent"
    app:shape_strokeSize="@dimen/stroke_1"
    app:shape_strokeColor="@color/border_default"
    app:shape_strokePressedColor="@color/border_strong"
    app:shape_textColor="@color/text_primary" />
```

## Card surface with a border

Replaces: `bg_card.xml`, or a `MaterialCardView` pulled in only for a corner radius.

```xml
<com.genesys.shape.layout.ShapeConstraintLayout
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:padding="@dimen/spacing_16"
    app:shape_radius="@dimen/radius_16"
    app:shape_solidColor="@color/surface_card"
    app:shape_strokeSize="@dimen/stroke_1"
    app:shape_strokeColor="@color/border_subtle" />
```

## Card with the designer's drop shadow

Replaces: a nine-patch, or `android:elevation` that does not match the mock.

```xml
<com.genesys.shape.layout.ShapeFrameLayout
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    app:shape_radius="@dimen/radius_16"
    app:shape_solidColor="@color/surface_card"
    app:shape_effect1Type="dropShadow"
    app:shape_effect1Color="@color/shadow_card"
    app:shape_effect1Blur="16dp"
    app:shape_effect1Spread="0dp"
    app:shape_effect1OffsetY="4dp"
    app:shape_effectPadContent="true" />
```

The Figma shadow's x/y/blur/spread map one-to-one. `shape_effectPadContent="true"` keeps
the shadow from being clipped by the content box. For a two-layer shadow, add a
`shape_effect2*` group — slot 1 paints first, so put the tight shadow there.

## Gradient CTA

Replaces: `bg_gradient_cta.xml`.

```xml
<com.genesys.shape.view.ShapeButton
    android:layout_width="match_parent"
    android:layout_height="52dp"
    android:text="@string/action_upgrade"
    app:shape_radius="@dimen/radius_pill"
    app:shape_solidGradientStartColor="@color/gradient_start"
    app:shape_solidGradientEndColor="@color/gradient_end"
    app:shape_solidGradientOrientation="startToEnd" />
```

Three stops: add `shape_solidGradientCenterColor`. Angled: pick the matching orientation
enum (`topStartToBottomEnd` and friends) rather than rotating the view.

## Gradient text

Replaces: a custom `TextView` with a `LinearGradient` shader in `onDraw`.

```xml
<com.genesys.shape.view.ShapeTextView
    android:layout_width="wrap_content"
    android:layout_height="wrap_content"
    android:text="@string/premium_title"
    android:textAppearance="@style/TextAppearance.App.HeadlineSmall"
    app:shape_textStartColor="@color/gradient_start"
    app:shape_textEndColor="@color/gradient_end"
    app:shape_textGradientOrientation="horizontal" />
```

## Selectable chip / tab

Replaces: `bg_chip_selector.xml` + `color/chip_text_selector.xml`.

```xml
<com.genesys.shape.view.ShapeTextView
    android:id="@+id/chipAll"
    android:layout_width="wrap_content"
    android:layout_height="36dp"
    android:gravity="center"
    android:paddingHorizontal="@dimen/spacing_16"
    android:text="@string/filter_all"
    app:shape_radius="@dimen/radius_pill"
    app:shape_solidColor="@color/chip_idle"
    app:shape_solidSelectedColor="@color/brand_primary"
    app:shape_textColor="@color/text_secondary"
    app:shape_textSelectedColor="@color/on_brand" />
```

Then `binding.chipAll.isSelected = state.filter == Filter.ALL`. No selector files, no
`setBackgroundResource` in the bind, and the recycled holder can never keep a stale
background.

## Bottom-sheet header with a drag handle

The pattern this codebase already uses.

```xml
<com.genesys.shape.layout.ShapeLinearLayout
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:gravity="center_horizontal"
    android:orientation="vertical"
    android:paddingHorizontal="@dimen/spacing_24"
    android:paddingTop="@dimen/spacing_8"
    app:shape_radiusInTopStart="@dimen/radius_32"
    app:shape_radiusInTopEnd="@dimen/radius_32"
    app:shape_solidColor="@color/surface_sheet">

    <com.genesys.shape.view.ShapeView
        android:layout_width="48dp"
        android:layout_height="4dp"
        android:layout_marginBottom="@dimen/spacing_16"
        app:shape_radius="100dp"
        app:shape_solidColor="@color/handle_muted" />

</com.genesys.shape.layout.ShapeLinearLayout>
```

## Divider

Replaces: a `View` with `android:background="@color/divider"`, which is the same thing but
does not survive a state or a rounded end.

```xml
<com.genesys.shape.view.ShapeView
    android:layout_width="match_parent"
    android:layout_height="1dp"
    app:shape_solidColor="@color/divider" />
```

## Dashed drop zone

Replaces: `bg_dashed.xml`.

```xml
<com.genesys.shape.layout.ShapeFrameLayout
    android:layout_width="match_parent"
    android:layout_height="120dp"
    app:shape_radius="@dimen/radius_12"
    app:shape_solidColor="@color/surface_muted"
    app:shape_strokeSize="@dimen/stroke_1"
    app:shape_strokeColor="@color/border_default"
    app:shape_strokeDashSize="6dp"
    app:shape_strokeDashGap="4dp" />
```

## Ripple on a tappable row

```xml
<com.genesys.shape.layout.ShapeLinearLayout
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:clickable="true"
    android:focusable="true"
    app:shape_radius="@dimen/radius_12"
    app:shape_solidColor="@color/surface_card"
    app:shape_ripple_enabled="true"
    app:shape_ripple_color="@color/ripple_default" />
```

A ripple on a view that is not clickable never draws. Give it `clickable`/`focusable` or a
click listener, or drop the attributes.

## Ring — progress backdrop, avatar frame

```xml
<com.genesys.shape.view.ShapeView
    android:layout_width="64dp"
    android:layout_height="64dp"
    app:shape_type="ring"
    app:shape_ringInnerRadiusRatio="3"
    app:shape_ringThicknessSize="4dp"
    app:shape_solidColor="@color/track_muted" />
```

## Rounded remote image

`ShapeImageView` gives the frame; Glide's transformation rounds the bitmap itself. Use
both — the frame alone leaves square bitmap corners poking out.

```xml
<com.genesys.shape.view.ShapeImageView
    android:id="@+id/imgThumb"
    android:layout_width="96dp"
    android:layout_height="96dp"
    android:scaleType="centerCrop"
    app:shape_radius="@dimen/radius_12"
    app:shape_strokeSize="@dimen/stroke_1"
    app:shape_strokeColor="@color/border_subtle" />
```

See the `image-loading-glide` skill for the load side.
