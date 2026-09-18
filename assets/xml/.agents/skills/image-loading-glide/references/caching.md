# Caching & Memory Management

`GlideImageView` (`com.github.impeterwayne:GlideImageView`, package `com.genesys.glideimageview`) provides declarative XML and programmatic Kotlin controls over disk and in-memory caching, with sensible defaults tailored for Android applications.

---

## 1. Overview & Default Behavior

By default:
- **Remote URLs and custom models** use Glide's standard caching strategy (`AUTOMATIC` disk cache, in-memory cache enabled).
- **Packaged APK resources** (drawables, mipmaps, `android.resource://` URIs) are **not cached by default**. Because these assets already reside unpacked or easily readable inside the APK, caching them duplicates storage in memory and on disk. Specifically:
  - `DiskCacheStrategy.NONE`
  - `skipMemoryCache(true)`

You can override these defaults at any time per-view (in XML or Kotlin) or process-wide.

---

## 2. Declarative XML Attributes

Configure caching strategies directly in your layout XML without writing any Kotlin code:

```xml
<com.genesys.glideimageview.GlideImageView
    android:id="@+id/bannerImage"
    android:layout_width="match_parent"
    android:layout_height="180dp"
    android:scaleType="centerCrop"
    app:glideSrc="https://example.com/banner.jpg"
    app:glideCacheType="none"
    app:glideSkipMemoryCache="true" />
```

| XML Attribute | Type | Values | Default | Description |
|---|---|---|---|---|
| `app:glideCacheType` | `enum` | `all`, `none`, `data`, `resource`, `automatic` | unset (inherits default) | Maps to Glide's `DiskCacheStrategy` |
| `app:glideSkipMemoryCache` | `boolean` | `true`, `false` | `false` | Skips Glide's in-memory LRU bitmap cache |

---

## 3. Cache Types

The `CacheType` enum (`com.genesys.glideimageview.CacheType`) maps directly to Glide's `DiskCacheStrategy`:

| CacheType | Glide Strategy | Description | Best Used For |
|---|---|---|---|
| `ALL` | `DiskCacheStrategy.ALL` | Caches both original data and decoded/transformed resource | Remote images frequently loaded in different sizes |
| `NONE` | `DiskCacheStrategy.NONE` | Disables disk cache completely | Sensitive data, packaged drawables, frequently changing dynamic images |
| `DATA` | `DiskCacheStrategy.DATA` | Writes data to disk cache before decoding | Remote images loaded from slow or metered networks |
| `RESOURCE` | `DiskCacheStrategy.RESOURCE` | Writes resources to disk cache after decoding and applying shapes/transformations | Images with expensive custom transformations |
| `AUTOMATIC` | `DiskCacheStrategy.AUTOMATIC` | Intelligent default choice based on data source type | General remote image loading |

---

## 4. Programmatic Kotlin API

You can configure caching on individual views or build immutable `ImageOptions`:

### Direct View Properties
```kotlin
// Disable disk cache and memory cache for dynamic content
imageView.cacheType = CacheType.NONE
imageView.skipMemoryCache = true
imageView.load("https://example.com/live_feed.jpg")
```

### Via Immutable `ImageOptions`
```kotlin
val options = ImageOptions(
    cacheType = CacheType.RESOURCE,
    skipMemoryCache = false
)

imageView.options = options
```

### Process-Wide Defaults
Set defaults once during `Application.onCreate()`:

```kotlin
GlideImageViewConfig.defaults = ImageOptions(
    cacheType = CacheType.AUTOMATIC,
    skipMemoryCache = false
)
```

---

## 5. Cache Key Signatures & Invalidation

Glide automatically builds cache keys using image URLs or resource IDs. When images at the same URL change on the server or when local files are updated, use cache signatures to invalidate the cache.

### Dynamic Content Invalidation (`ObjectKey`)
```kotlin
// Per-view signature
imageView.signature = ObjectKey(user.avatarUpdatedAt)

// Or using ImageOptions
imageView.options = imageView.options.withSignature(
    ObjectKey(localFile.lastModified())
)
```

### Local Resource Version Invalidation
For packaged drawable resources that you intentionally disk-cache, AAPT can reassign resource IDs between application builds. To prevent stale drawables after an app update, use Glide's `ApplicationVersionSignature`:

```kotlin
imageView.signature = ApplicationVersionSignature.obtain(context)

// Or register globally via a RequestDecorator:
GlideImageViewConfig.decorators += RequestDecorator { context, request ->
    request.signature(ApplicationVersionSignature.obtain(context))
}
```

---

## 6. Precedence Order

When multiple cache settings are applied, `GlideImageView` resolves them in the following order (highest precedence wins):

1. **View Runtime Properties / `image.options`** (highest)
2. **XML Attributes** (`app:glideCacheType`, `app:glideSkipMemoryCache`)
3. **Styles and Theme Attributes**
4. **`GlideImageViewConfig.defaults`**
5. **Packaged Resource Defaults** (`DiskCacheStrategy.NONE` for APK resources)
6. **Glide System Defaults** (lowest)
