---
name: image-loading-glide
description: Use when loading images into Android Views with GlideImageView (com.github.impeterwayne:GlideImageView, package com.genesys.glideimageview) in an XML-layout project - the declarative GlideImageView custom view with instant Layout Editor preview (app:glideSrc, glidePlaceholder, glideError, glideRadius, glideCircle, glideCrossFade, glideCrossFadeDuration, glideCacheType, glideSkipMemoryCache), shape transformations (Shape.Circle, Shape.RoundedCorners, Squircle, Border, Grayscale), caching strategies, programmatic loading (load, loadAsset, clear), process-wide defaults, and extensions (ModelResolver, Shape, RequestDecorator). The XML-track counterpart to Landscapist GlideImage.
---

# Glide image loading for XML layouts

`GlideImageView` (`com.github.impeterwayne:GlideImageView`, package `com.genesys.glideimageview.GlideImageView`) is the standard declarative image loader for Android XML layouts. Every remote URL, asset path, file path, `Uri`, and drawable resource goes through it.

A manual `BitmapFactory.decodeStream` into `setImageBitmap`, or a second image loader alongside Glide, is a defect.

## Setup

```gradle
// settings.gradle — repositories
maven { url 'https://jitpack.io' }

// module build.gradle
implementation 'com.github.impeterwayne:GlideImageView:1.0.0'
```

Requires `minSdk` 23+, `compileSdk` 36, Java 17. In projects using version catalogs, reference `libs.glide.image.view`.

## 1. `GlideImageView` — the layout says what it loads

A declarative `AppCompatImageView` subclass. The source and its options live directly in the layout, with **instant live preview inside the Android Studio Layout Editor** for drawables and assets:

```xml
<com.genesys.glideimageview.GlideImageView
    android:id="@+id/imgThumb"
    android:layout_width="96dp"
    android:layout_height="96dp"
    android:scaleType="centerCrop"
    app:glideSrc="images/banner.webp"
    app:glidePlaceholder="@drawable/ic_thumb_placeholder"
    app:glideError="@drawable/ic_thumb_error"
    app:glideRadius="@dimen/radius_12"
    app:glideCrossFade="true"
    app:glideCacheType="automatic" />
```

| Attribute | Effect |
| :--- | :--- |
| `app:glideSrc` | source string or reference — `@drawable/...`, asset path `images/...`, remote URL `https://...`, file, or URI |
| `app:glidePlaceholder` | drawable shown while loading (and in Layout Editor for remote URLs) |
| `app:glideError` | drawable shown on failure |
| `app:glideRadius` | corner radius in dp/dimen; combines with the scale transformation implied by `scaleType` |
| `app:glideCircle` | circle crop; wins over `glideRadius` |
| `app:glideCrossFade` | cross-fade transition on image load |
| `app:glideCrossFadeDuration` | cross-fade animation duration in ms (default: 300ms) |
| `app:glideCacheType` | disk cache strategy: `all`, `none`, `data`, `resource`, `automatic` |
| `app:glideSkipMemoryCache` | boolean: bypasses Glide's in-memory bitmap pool/cache |

### Live Layout Editor Preview
- **Drawable resources (`@drawable/...`)**: Direct references to app drawables render immediately in design mode.
- **Asset paths (`images/...`)**: Decoded live from `src/main/assets/` during edit mode (`isInEditMode`), so you see actual design assets right inside Android Studio without launching an emulator.
- **Remote URLs (`https://...`)**: Safely display `app:glidePlaceholder` in edit mode.

## 2. Programmatic Loading (Kotlin)

When sources change dynamically at runtime (in adapters, view holders, or response callbacks):

```kotlin
// Load remote URL, resource id, or domain model
binding.imgThumb.load(item.thumbnailUrl)

// Load asset path directly
binding.imgThumb.loadAsset("images/banner.webp")

// Clear in-flight load and reset image
binding.imgThumb.clear()
```

### Composable Shapes & Runtime Options

```kotlin
// Apply shape transformations
binding.imgThumb.shapes = listOf(
    Shape.RoundedCorners(resources.getDimensionPixelSize(R.dimen.radius_12))
)

// Mutate options cleanly
binding.imgThumb.updateOptions {
    copy(crossFade = true, crossFadeDurationMs = 200)
}
```

## 3. The Reference Material

| Read this | For |
| :--- | :--- |
| [references/glide-image-view.md](./references/glide-image-view.md) | full XML attribute catalog, Kotlin API (`load`, `loadAsset`, `clear`), Epoxy list integration, and legacy `ImageView.loadImage(...)` helper |
| [references/extensions.md](./references/extensions.md) | architecture and extension points: custom `ModelResolver` (domain models, auth headers), composable `Shape`s, `RequestDecorator`, `RequestManagerFactory`, `OnLoadListener`, and subclassing |
| [references/caching.md](./references/caching.md) | caching policy (APK resources bypass cache by default), XML cache attributes, `CacheType` enum, cache invalidation via `ObjectKey` / `ApplicationVersionSignature`, and precedence order |

## 4. Process-Wide Defaults & Telemetry

Configure standard placeholders, error states, or telemetry once process-wide via `GlideImageViewConfig` in `Application.onCreate()`:

```kotlin
GlideImageViewConfig.defaults = ImageOptions(
    placeholder = R.drawable.ic_thumb_placeholder,
    error = R.drawable.ic_thumb_error,
    crossFade = true
)

GlideImageViewConfig.listeners += object : OnLoadListener {
    override fun onLoadFailed(view: GlideImageView, error: GlideException?) {
        // App-wide telemetry or error reporting
    }
}
```

## Rules that are not negotiable

**Placeholder and error, always.** A load with neither is a blank box on a slow network and a blank box forever on a 404. If the design does not specify one, use the neutral placeholder the project already has.

**Clear in the Epoxy model's `unbind()`.** This is the single most common Glide bug in a list:

```kotlin
override fun ItemDocumentBinding.bind() {
    imgThumb.load(document?.thumbnailUrl)
}

override fun ItemDocumentBinding.unbind() {
    imgThumb.clear()
}
```

Without `unbind()`, an in-flight request on a recycled view completes after reuse and paints the previous row's image over the new row. Calling `imgThumb.clear()` cancels the pending Glide request immediately.

**Packaged APK drawables are not cached by default.** When loading `@drawable/...`, `@mipmap/...`, or `android.resource://`, `GlideImageView` automatically uses `DiskCacheStrategy.NONE` and `skipMemoryCache(true)` because the bytes already live inside the APK. Do not force disk caching on packaged assets unless you explicitly require it.

**Round with a transformation, not a pre-cut asset.** Use `app:glideRadius` or `app:glideCircle` (or `Shape.RoundedCorners` / `Shape.Circle`). `GlideImageView` ensures the scale transformation from `scaleType` is preserved so the bitmap does not distort. Where the frame also requires borders or drop shadows, wrap with a `ShapeImageView` (`shape-view` skill).

**`dontAnimate()` in lists unless crossfade is specified.** Crossfading on every scroll-in creates visual flicker in fast-scrolling lists.

## Checklist

- [ ] Dependency `com.github.impeterwayne:GlideImageView:1.0.0` is present.
- [ ] Every load declares a placeholder and an error drawable.
- [ ] Epoxy item models call `imgThumb.clear()` in `unbind()`.
- [ ] Rounded images use `app:glideRadius` or `app:glideCircle` rather than pre-rounded PNGs.
- [ ] Packaged APK drawables rely on the default zero-overhead cache bypass.
- [ ] No second image loader, and no manual `BitmapFactory` decode.
- [ ] Meaningful images carry an `android:contentDescription`; decorative ones are `@null`.
