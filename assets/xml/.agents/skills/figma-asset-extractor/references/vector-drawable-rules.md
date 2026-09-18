# Android VectorDrawable & Asset Extraction Rules

## 1. Icon Container Node Selection (CRITICAL)

When exporting vector icons from Figma:
- **ALWAYS** select the outermost container node (`COMPONENT` or `FRAME` bounding box, e.g. `24x24`, `32x32`), **DO NOT** select internal child `VECTOR` paths.
- Selecting the container node ensures:
  - Preserved standard `viewportWidth` and `viewportHeight` (e.g., 24dp x 24dp).
  - Preserved padding/insets according to design system specifications.

---

## 2. Naming Conventions & Resource Policy

- **VectorDrawable File Names**: Must follow `ic_<feature_or_name>.xml`.
- **Allowed Characters**: Lowercase `a-z`, digits `0-9`, and underscore `_` only. Never use hyphens `-`, spaces, special characters, or uppercase letters.
- **Resource Reuse Check**: Before exporting a new icon, check existing drawables in `res/drawable/` across the project as per `android-resource-policy`.
- **Target Directories**:
  - App-wide common icons: `core/ui/src/main/res/drawable/` or `app/src/main/res/drawable/`.
  - Feature-specific icons: `feature/<feature-name>/src/main/res/drawable/`.

---

## 3. Vector Conversion Parameters Guide

When calling `convert_svg_to_android_drawable`:

| Parameter | Recommended Value | Explanation |
|---|---|---|
| `fillBlack` | `false` (default) | Set to `true` **only if** the exported vector renders blank/invisible due to missing fill attributes in Figma. |
| `floatPrecision` | `6` (or 3-6) | Decimal precision for path coordinates. 6 provides maximum fidelity for 24dp/48dp icons. |
| `xmlTag` | `false` | Android resource XML files do not need the `<?xml ...?>` header declaration. |
| `tint` | Unset / `#FF...` | Leave unset if the icon will be tinted at the call site (`app:tint="@color/..."`). Set only if the icon has a permanent hardcoded tint. |

---

## 4. Temporary File Cleanup

- `save_screenshots` exports temporary SVG files to a scratch/temp folder (e.g., `.agents/scratch/temp_svgs/`).
- `convert_svg_to_android_drawable` automatically cleans up source SVG files after successful conversion.
- Ensure no orphaned SVG files remain in the repository.

---

## 5. XML Image & Icon Rendering

- **Vector Icons**: Use `app:srcCompat="@drawable/ic_*"` on an `ImageView` or `ShapeImageView`, tinted with `app:tint="@color/..."`.
- **Dynamic Images**: Use `GlideImageView` (`app:glideSrc`, `app:glidePlaceholder`, `app:glideError`) or the `ImageView.loadImage(...)` extension. Every load declares a placeholder and an error drawable.
