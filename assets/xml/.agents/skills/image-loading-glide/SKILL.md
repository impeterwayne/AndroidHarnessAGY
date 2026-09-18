---
name: image-loading-glide
description: Use when loading images into Android Views with Glide (com.github.bumptech.glide) in an XML-layout project - the declarative GlideImageView custom view (app:glideSrc, glidePlaceholder, glideError, glideRadius, glideCircle, glideCrossFade), the ImageView.loadImage extension, transformations, clearing in an Epoxy model's unbind, and cache strategy. The XML-track counterpart to Landscapist GlideImage.
---

# Glide image loading for XML layouts

Glide is the only image loader in this project. Every remote URL, file path, `Uri`,
resource id and byte array goes through it. A manual `BitmapFactory.decodeStream` into
`setImageBitmap`, or a second loader alongside it, is a defect.

There are two call shapes, in order of preference.

## 1. `GlideImageView` — the layout says what it loads

A declarative `AppCompatImageView` subclass. The source and its options live in the
layout, so a static image needs no binding code at all, and the Studio preview renders
asset-backed sources.

```xml
<com.<app>.ui.component.custom.GlideImageView
    android:id="@+id/imgThumb"
    android:layout_width="96dp"
    android:layout_height="96dp"
    android:scaleType="centerCrop"
    app:glidePlaceholder="@drawable/ic_thumb_placeholder"
    app:glideError="@drawable/ic_thumb_error"
    app:glideRadius="@dimen/radius_12"
    app:glideCrossFade="true" />
```

```kotlin
holder.binding.imgThumb.glideSrc = item.thumbnailUrl
```

| Attribute | Effect |
| :--- | :--- |
| `app:glideSrc` | source string — http(s), content, file, android.resource, or a bare path treated as `file:///android_asset/…` |
| `app:glidePlaceholder` | drawable shown while loading |
| `app:glideError` | drawable shown on failure |
| `app:glideRadius` | corner radius; combines with the scale transformation implied by `scaleType` |
| `app:glideCircle` | circle crop; wins over `glideRadius` |
| `app:glideCrossFade` | cross-fade in, instead of `dontAnimate()` |

Setting `glideSrc` to null or blank clears the view and cancels the request. Options are
an immutable `Options` data class — `updateOptions { copy(isCircle = true) }` triggers a
reload; assigning the same value does not.

If the project has no such view yet, add it once in the shared UI module rather than
open-coding Glide chains per screen. The implementation is in
[references/glide-image-view.md](./references/glide-image-view.md) — copy it, adjust the
package and `R.styleable` name, and declare the `declare-styleable` block it needs.

## 2. `ImageView.loadImage(...)` — the extension

For an ordinary `ImageView` already in a layout, or a load whose options are computed.

```kotlin
fun ImageView.loadImage(
    source: Any?,
    @DrawableRes placeholder: Int = 0,
    @DrawableRes error: Int = 0,
    radiusPx: Int = 0,
    circle: Boolean = false,
    skipCache: Boolean = false
)
```

Full implementation in [references/glide-image-view.md](./references/glide-image-view.md).

## 3. A raw `Glide.with(...)` chain

Only when neither of the above fits — an `asBitmap()` load, a custom `Target`, a
`RequestListener` for analytics. Even then, keep the chain at the binding site and do not
spread it across helpers.

```kotlin
Glide.with(this)
    .asBitmap()
    .load(uri)
    .into(object : CustomTarget<Bitmap>() { … })
```

## Rules that are not negotiable

**Placeholder and error, always.** A load with neither is a blank box on a slow network
and a blank box forever on a 404. If the design does not give one, use the neutral
placeholder the project already has.

**Scope `Glide.with()` to the narrowest lifecycle available** — `Glide.with(view)` inside
an adapter, `Glide.with(fragment)` inside a Fragment. `Glide.with(context)` with an
application context keeps the request alive past the screen and leaks the target.

**Clear in the Epoxy model's `unbind()`.** This is the single most common Glide bug in a
list:

```kotlin
override fun ItemDocumentBinding.bind() {
    imgThumb.glideSrc = document?.thumbnailUrl
}

override fun ItemDocumentBinding.unbind() {
    Glide.with(imgThumb).clear(imgThumb)
}
```

Without it, a slow request completes into a holder that now shows a different row.
`GlideImageView` also cancels its own request when `glideSrc` is reassigned, including to
null — but `unbind()` is what covers the holder leaving the screen entirely.

**Round with a transformation, not a crop tool.** `RoundedCorners(px)` combined with the
scale transformation your `scaleType` implies (`CenterCrop`, `FitCenter`,
`CenterInside`) — a `RoundedCorners` on its own silently drops the scaling and the image
distorts. `CircleCrop()` for avatars. Never ship a pre-rounded PNG. Where the frame also
needs a border, put a `ShapeImageView` around it (`shape-view` skill) and keep the bitmap
transformation too — the frame alone leaves square bitmap corners showing.

**Size the request.** Loading a 4000 px photo into a 96 dp thumbnail wastes memory even
with `centerCrop`. `override(width, height)` when the view has no fixed size at request
time.

**Cache deliberately.** `DiskCacheStrategy.ALL` is the right default for remote content.
Use `DiskCacheStrategy.NONE` + `skipMemoryCache(true)` only for content that genuinely
changes behind a stable URL — a re-cropped avatar, a regenerated thumbnail — and say why
at the call site by naming the helper `loadImageNoCache` rather than by a comment.

**`dontAnimate()` in lists** unless the design asks for a cross-fade. A cross-fade on every
scroll-in reads as flicker.

## Setup

```gradle
implementation "com.github.bumptech.glide:glide:$glide_version"
ksp "com.github.bumptech.glide:ksp:$glide_version"
```

The `ksp`/annotation-processor artifact is only needed for `@GlideModule` generated API.
If the project has no `AppGlideModule`, the runtime artifact alone is enough — do not add
a processor to a module that will not use it.

## Checklist

- [ ] Every load declares a placeholder and an error drawable.
- [ ] `Glide.with()` is scoped to the view or fragment, never an application context.
- [ ] Epoxy item models clear in `unbind()`.
- [ ] Rounded loads combine `RoundedCorners` with the scale transformation.
- [ ] No second image loader, and no manual bitmap decode.
- [ ] Meaningful images carry an `android:contentDescription`; decorative ones are
      explicitly `@null`.
- [ ] Cache strategy is the default unless there is a stated reason.
