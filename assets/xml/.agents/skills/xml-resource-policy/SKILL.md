---
name: xml-resource-policy
description: Use when managing Android resources for View/XML UI work - strings and plurals, colours and night mode, dimens, text appearance styles and themes, fonts, vector drawables and icons, selectors, localization and RTL, and the reuse policy that decides whether a value becomes a resource at all. The XML-track counterpart to android-resource-policy.
---

# Resource policy for XML layouts

The design tokens of an XML project are its `res/values` files. Every colour, every
repeated dimension and every piece of user-facing text is a resource, and the layout
references it. The layout is a view of the design system, not a place to restate it.

## 1. Guiding principles

1. Follow the conventions already in the project. Read `res/values` before adding to it.
2. Reuse an existing resource before declaring a new one. A near-duplicate colour is worse
   than a shared one.
3. Values that affect the design system are always resources. Genuine one-offs — a `16dp`
   margin used once, on one screen — can stay inline.
4. Never hardcode a user-facing string, and never hardcode a colour anywhere but
   `colors.xml`.

## 2. The table

| Resource | Do | Don't |
| :--- | :--- | :--- |
| **Strings** | `res/values/strings.xml`; `@string/…` in the layout, `getString(...)` in code. Counts use `<plurals>`. Formatting uses `%1$s` placeholders. | Literal `android:text="Continue"`. String concatenation in code — it breaks every translation. |
| **Dynamic text** | Passed through state and set in `render` or an Epoxy `bind()`. | Putting an API-sourced value into `strings.xml`. |
| **Content descriptions** | `cd_*` strings on every meaningful `ImageView` and icon button. Decorative images get `android:contentDescription="@null"` explicitly. | Leaving it unset — that is the accessibility lint everyone suppresses and nobody fixes. |
| **Colours** | `@color/*` from `colors.xml`, with a `values-night/colors.xml` counterpart where the app has a dark theme. Stateful colours as a `res/color/*.xml` selector **only** where a `Shape*` view's state attributes cannot express it. | Raw `#RRGGBB` in a layout, a style or Kotlin. `@android:color/*` for anything but `transparent`. |
| **Dimensions** | `@dimen/*` for anything repeated: radii, strokes, spacing scale, icon sizes. | Mechanically extracting every value — a lone inline `16dp` is fine. Repeating `12dp` across nine layouts is not. |
| **Typography** | `android:textAppearance="@style/TextAppearance.App.BodyLarge"` from `typography.xml`. | A loose `textSize` + `fontFamily` + `lineHeight` triple repeated per screen. Hardcoded `sp` outside the appearance styles. |
| **Fonts** | `res/font/*` and font families, referenced from the text appearance. | Loading a `Typeface` from assets in code. |
| **Icons** | Vector `res/drawable/ic_<name>.xml`, rendered with `app:srcCompat`. Tinted with `app:tint="@color/…"` rather than duplicated per colour. | A PNG set for a flat 1–2 colour icon. Checking in the same glyph twice in two colours. |
| **Backgrounds, corners, borders, shadows** | `app:shape_*` on a `Shape*` view — see `shape-view`. | A new `<shape>`, `<selector>` or `<ripple>` in `res/drawable`. |
| **Remote and dynamic images** | Glide, with a placeholder and an error drawable — see `image-loading-glide`. | A second image loader. A manual bitmap decode. |
| **Styles** | A `<style>` for a widget treatment that repeats: `Widget.App.Button.Primary`, applied with `style="…"`. | A style holding one screen's one-off layout params. Styles that inherit from nothing. |
| **Themes** | `themes.xml` (+ `values-night`) for the app and Activity themes; `?attr/…` to read a theme value. | Per-screen theme forks to change one colour. |
| **Localization & RTL** | `start`/`end`, never `left`/`right`. `paddingHorizontal`/`paddingVertical` where both sides match. `values-<lang>` for translations. | Layouts locked to left/right. Fixed widths sized to one language's string. |

## 3. Where things live

| File | Holds |
| :--- | :--- |
| `res/values/strings.xml` | strings, plurals, `cd_*` content descriptions |
| `res/values/colors.xml` | every colour literal in the app |
| `res/values-night/colors.xml` | the dark overrides |
| `res/values/dimens.xml` | the spacing, radius, stroke and icon-size scale |
| `res/values/typography.xml` | `TextAppearance.App.*` |
| `res/values/styles.xml` | `Widget.App.*` and dialog/sheet styles |
| `res/values/themes.xml` | app and Activity themes |
| `res/values/attrs.xml` | `declare-styleable` for custom views |
| `res/drawable/` | vector icons `ic_*`, layer-lists, animated selectors |
| `res/font/` | font files and families |
| `res/layout/` | `activity_*`, `fragment_*`, `item_*`, `dialog_*`, `view_*` |

In a multi-module project, shared resources live in `core/ui`; a string or drawable used by
one feature stays in that feature's `res`. Moving it to `core/ui` happens when the second
consumer appears — not in anticipation of one.

## 4. Naming

- Strings: `<screen>_<purpose>` — `home_title`, `home_empty_message`, `action_continue`,
  `error_network`. Content descriptions: `cd_<what>` — `cd_close`, `cd_document_thumbnail`.
- Colours: name by role where the design system has roles (`surface_card`,
  `text_secondary`, `border_subtle`, `brand_primary`), by value only in the raw palette
  layer if the project keeps one. A colour named `color_627B89` cannot be redefined for
  night mode without lying.
- Dimens: `spacing_16`, `radius_12`, `stroke_1`, `icon_24`.
- Drawables: `ic_*` for icons, `img_*` for raster artwork, `bg_*` only for backgrounds that
  genuinely have to stay drawables.
- Layouts: see `android-xml-views` → module structure.

Match the project's existing scheme where it differs from the above. Consistency beats the
better naming convention introduced halfway through a codebase.

## 5. Before adding a resource

1. `grep` the value. A `#1E2025` that is about to become `surface_card` is usually already
   `@color/color_1E2025` somewhere.
2. `grep` the proposed name. Two modules can each declare `@string/title` and the merge
   picks one — silently.
3. Check the module. A resource in `core/ui` is visible to every feature; one in
   `feature/home` is not, and referencing it from another feature does not compile.
4. For a string, check `values-<lang>` — adding to the default file only is fine, but
   renaming an existing id orphans every translation of it.

## 6. Checklist

- [ ] No literal user-facing text in any layout or Kotlin file.
- [ ] No raw hex outside `colors.xml`.
- [ ] Counts use plurals; formatted text uses placeholders, not concatenation.
- [ ] Text styling goes through `textAppearance`, not loose attributes.
- [ ] Every meaningful image has a `contentDescription`; decorative ones say `@null`.
- [ ] `start`/`end` throughout.
- [ ] Repeated dimensions are `@dimen`; one-offs may stay inline.
- [ ] Icons are vectors in `res/drawable/ic_*`, tinted rather than duplicated.
- [ ] No new `<shape>` / `<selector>` / `<ripple>` drawable — ShapeView attributes instead.
- [ ] New resources live in the narrowest module that needs them.
- [ ] `./gradlew :<module>:assembleDebug` passes — a missing or misspelled resource is a
      link-time failure that `compileDebugKotlin` will not surface.
