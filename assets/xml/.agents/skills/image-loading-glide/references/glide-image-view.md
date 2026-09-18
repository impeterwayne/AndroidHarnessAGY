# `GlideImageView` Reference & API

`GlideImageView` (`com.github.impeterwayne:GlideImageView`, package `com.genesys.glideimageview.GlideImageView`) is the declarative, zero-boilerplate image loading view for Android XML layouts.

---

## Dependency Setup

Add JitPack to your repository list and include the dependency:

```groovy
// settings.gradle
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        maven { url 'https://jitpack.io' }
    }
}

// build.gradle
dependencies {
    implementation 'com.github.impeterwayne:GlideImageView:1.0.0'
}
```

Or with Kotlin DSL (`settings.gradle.kts` / `build.gradle.kts`):

```kotlin
// settings.gradle.kts
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://jitpack.io") }
    }
}

// build.gradle.kts
dependencies {
    implementation("com.github.impeterwayne:GlideImageView:1.0.0")
}
```

---

## Layout XML Attributes

```xml
<com.genesys.glideimageview.GlideImageView
    android:id="@+id/bannerImage"
    android:layout_width="match_parent"
    android:layout_height="200dp"
    android:scaleType="centerCrop"
    app:glideSrc="images/banner.webp"
    app:glidePlaceholder="@drawable/ic_placeholder"
    app:glideError="@drawable/ic_error"
    app:glideRadius="@dimen/radius_12"
    app:glideCrossFade="true"
    app:glideCrossFadeDuration="300"
    app:glideCacheType="automatic"
    app:glideSkipMemoryCache="false" />
```

| Attribute | Format | Description |
|---|---|---|
| `app:glideSrc` | `string\|reference` | **Primary source:** drawable resource (`@drawable/...`), asset path (`images/...`), remote URL (`https://...`), file, or URI |
| `app:glidePlaceholder` | `reference` | Drawable resource shown while loading |
| `app:glideError` | `reference` | Drawable resource shown when load fails |
| `app:glideRadius` | `dimension` | Corner radius in dp/dimen (adds `Shape.RoundedCorners`, respecting `scaleType`) |
| `app:glideCircle` | `boolean` | Circular crop (adds `Shape.Circle`, wins over `glideRadius`) |
| `app:glideCrossFade` | `boolean` | Enables crossfade transition animation |
| `app:glideCrossFadeDuration` | `integer` | Crossfade duration in milliseconds (default: 300ms) |
| `app:glideCacheType` | `enum` | Disk cache strategy: `all`, `none`, `data`, `resource`, `automatic` |
| `app:glideSkipMemoryCache` | `boolean` | Bypasses Glide's in-memory LRU bitmap cache (default: false) |

---

## Live Layout Editor Preview

Standard image views appear as blank gray boxes in Android Studio design view. With `app:glideSrc`, **drawables and assets render live inside the Layout Editor**:

- **Drawable resources (`@drawable/...`, `@mipmap/...`)**: Preview live in design mode and compose with shapes (`app:glideCircle`, `app:glideRadius`).
- **Asset paths (`images/...`)**: Decoded directly from `src/main/assets/` during edit mode (`isInEditMode`), showing real artwork without compiling or running the app.
- **Remote URLs (`https://...`)**: Safely fall back to displaying `app:glidePlaceholder` in design mode.

---

## Programmatic Loading (Kotlin)

When sources change at runtime (in adapters, view holders, or upon user actions):

```kotlin
// Load remote URL, URI, File, or custom domain model
imageView.load(item.imageUrl)

// Load drawable resource directly
imageView.load(R.drawable.ic_avatar_default)

// Load asset path directly (e.g. assets/images/banner.webp)
imageView.loadAsset("images/banner.webp")

// Clear in-flight load and reset view
imageView.clear()
```

### Dynamic Configuration & Shapes

```kotlin
// Mutate options cleanly
imageView.updateOptions {
    copy(
        placeholder = R.drawable.ic_placeholder,
        error = R.drawable.ic_error
    )
}

// Apply composable shape transformations
imageView.shapes = listOf(
    Shape.RoundedCorners(resources.getDimensionPixelSize(R.dimen.radius_16))
)

// Caching controls
imageView.cacheType = CacheType.NONE
imageView.skipMemoryCache = true

// Cache invalidation signature
imageView.signature = ObjectKey(user.avatarUpdatedAt)
```

### Load Callbacks

```kotlin
// Add listener shorthand
val listener = imageView.addOnLoadListener(
    onStarted = { /* show progress bar */ },
    onReady = { drawable -> /* hide progress bar */ },
    onFailed = { exception -> /* log error */ },
    onCleared = { /* reset state */ }
)

// Remove when detached
imageView.removeOnLoadListener(listener)
```

---

## Binding in an Epoxy Item Model

In list rows built with Epoxy, always load in `bind()` and clear in `unbind()`:

```kotlin
@EpoxyModelClass
abstract class DocumentItemModel :
    BaseEpoxyViewBindingHolder<ItemDocumentBinding>(ItemDocumentBinding::bind) {

    @EpoxyAttribute
    open var document: DocumentModel? = null

    override fun getDefaultLayout(): Int = R.layout.item_document

    override fun ItemDocumentBinding.bind() {
        val data = document ?: return
        txtTitle.text = data.title
        imgThumb.load(data.thumbnailUrl)
    }

    override fun ItemDocumentBinding.unbind() {
        imgThumb.clear()
    }
}
```

The `unbind()` clear is critical: Epoxy recycles holders across rows, and an in-flight request that completes after reuse paints the wrong row's image. `imgThumb.clear()` cancels the pending Glide request immediately.

---

## Process-Wide Configuration (`GlideImageViewConfig`)

Configure application-wide defaults once in `Application.onCreate()`:

```kotlin
class App : Application() {
    override fun onCreate() {
        super.onCreate()

        // Default placeholder, error, and transitions
        GlideImageViewConfig.defaults = ImageOptions(
            placeholder = R.drawable.ic_placeholder_default,
            error = R.drawable.ic_error_default,
            crossFade = true,
            crossFadeDurationMs = 250
        )

        // Global load telemetry / error tracking
        GlideImageViewConfig.listeners += object : OnLoadListener {
            override fun onLoadFailed(view: GlideImageView, error: GlideException?) {
                FirebaseCrashlytics.getInstance().recordException(error ?: return)
            }
        }
    }
}
```

---

## Legacy `ImageView.loadImage(...)` Extension

For existing plain `ImageView`s in a layout that have not yet migrated to `GlideImageView`:

```kotlin
fun ImageView.loadImage(
    source: Any?,
    @DrawableRes placeholder: Int = 0,
    @DrawableRes error: Int = 0,
    radiusPx: Int = 0,
    circle: Boolean = false,
    skipCache: Boolean = false
) {
    if (source == null) {
        Glide.with(this).clear(this)
        setImageDrawable(null)
        return
    }

    var request = Glide.with(this).load(source)

    if (placeholder != 0) request = request.placeholder(placeholder)
    if (error != 0) request = request.error(error)

    request = when {
        circle -> request.transform(CircleCrop())
        radiusPx > 0 -> request.transform(CenterCrop(), RoundedCorners(radiusPx))
        else -> request
    }

    request = if (skipCache) {
        request.diskCacheStrategy(DiskCacheStrategy.NONE).skipMemoryCache(true)
    } else {
        request.diskCacheStrategy(DiskCacheStrategy.ALL)
    }

    request.dontAnimate().into(this)
}
```
