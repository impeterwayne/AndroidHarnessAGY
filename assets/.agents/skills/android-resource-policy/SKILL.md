---
name: android-resource-policy
description: Use when managing Android resources for UI work - strings, colors, dimensions, fonts, drawables, icons, localization, RTL, and resource reuse policy.
---
# android-resource-policy

This skill manages shared Android resources for Jetpack Compose UI. Apply when creating or modifying strings, colors, dimensions, fonts, drawables, icons, theme tokens, or resources related to localization/accessibility.

## 1. Guiding Principles

1. Adhere to existing resource conventions in the project first.
2. Reuse existing resources / design tokens before adding new ones.
3. Use the project's theme / design tokens (`AppTheme`) for colors, typography, spacing, shapes, and strokes.
4. Never hardcode reusable values or values affecting the design system.
5. Only keep local constants/values when they are one-off, clear, non-repeating, and extracting them to resources would add unnecessary noise.

## 2. Resource Management

| Rule | Do | Don't |
|------|----|-----|
| **Strings** | Static text uses `res/values/strings.xml` and `stringResource(...)`. Quantity-dependent text uses plurals. Text formatting uses placeholders. | Hardcoding user-facing text or concatenating strings manually, causing localization issues. |
| **Dynamic Text** | Text from APIs, databases, user input, or UI state is passed directly via state/models. | Placing dynamic text into `strings.xml`. |
| **Colors** | Use existing theme / design tokens in `AppTheme.colorScheme` / `Color.kt` per project convention. | Hardcoding hex values across UI code or bypassing the theme, breaking Light/Dark mode support. |
| **Dimensions & Spacing** | Use existing spacing tokens (`AppTheme.spacing`) and shape tokens (`AppTheme.shapes`) for design system elements. One-off `dp/sp` can remain local if clear. | Mechanically extracting every `dp/sp` or leaving repeated magic numbers everywhere. |
| **Fonts & Typography** | Use `AppTheme.typography` or fonts in `res/font`. | Arbitrarily instantiating fonts directly or fixing text size, breaking accessibility. |
| **Icons & Vectors** | Check existing `res/drawable` first. Monochromatic/2-color vector icons live in `res/drawable/ic_<name>.xml` and render with `Icon(painterResource(R.drawable.ic_*))`. NEVER USE `Icons.Default...` or Material defaults. | Using `Icons.Default...` or `@android:drawable/...` without checking project resources. |
| **Dynamic & Remote Images** | Use Landscapist `GlideImage` with `previewPlaceholder`, `loading`, and `failure` states. | Hardcoding image loaders or omitting loading/failure states. |
| **Localization & RTL** | Use `start/end` instead of `left/right` where appropriate. Use plurals, placeholders, and string resources to support translation. | Concatenating strings in fixed order or needlessly locking layouts to left/right. |

## 3. Directory Verification Before Adding Resources

- `res/values/`: strings (`strings.xml`), plurals.
- `res/drawable/`: vector icons (`ic_*.xml`), vector badges.
- `core/designsystem/src/main/java/.../theme/`: Kotlin design tokens (`AppTheme`, `Color.kt`, `Spacing.kt`, `Typography.kt`, `Theme.kt`, `Stroke.kt`).
- `res/font/`: font files and font families.
- `res/mipmap/`: launcher icons.

## 4. Checklist

- [ ] Existing matching resources in the project have been checked.
- [ ] User-facing static text uses string resources (`stringResource(...)`).
- [ ] Dynamic text from state/API/user input is not improperly placed in `strings.xml`.
- [ ] Quantity-based strings use plurals when necessary.
- [ ] Formatted strings use placeholders without manual string concatenation.
- [ ] Colors use `AppTheme.colorScheme` tokens and support Light/Dark mode.
- [ ] Vector icons are placed in `res/drawable/ic_*.xml`.
- [ ] Fonts use typography system (`AppTheme.typography`) or `res/font`.
- [ ] Layouts use `start/end` to properly support RTL.
- [ ] UI accommodates long text and large font scales gracefully.
