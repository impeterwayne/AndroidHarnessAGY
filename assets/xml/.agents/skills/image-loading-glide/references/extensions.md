# Extending GlideImageView

`GlideImageView` (`com.github.impeterwayne:GlideImageView`, package `com.genesys.glideimageview`) is designed from the ground up to be extensible without modifying library internals or resorting to view subclassing. The library separates concerns into composable seams that can be configured globally (process-wide) or tuned per-view.

---

## Architecture Overview

Whenever an image is loaded, `GlideImageView` processes the request through three primary extension seams in a deterministic order:

```
Source Model (Any?) ──► [ 1. ModelResolver ] ──► Resolved Model (e.g. GlideUrl, Uri, File)
                                                        │
Bitmap Rendering    ◄── [ 2. Shape ]         ◄── [ 3. RequestDecorator ]
(ScaleType & Mask)      (Transformations)        (Glide Request Options)
```

1. **`ModelResolver`** — Decides **what** gets loaded by intercepting the input model and converting it into a model Glide understands.
2. **`RequestDecorator`** — Configures **how** Glide loads it (caching, priorities, thumbnails, sizing).
3. **`Shape`** — Determines **how the bitmap is transformed and displayed** (masks, borders, effects).

---

## 1. `ModelResolver` — Resolving Data Sources

The `source` passed to `image.load(...)` or `app:glideSrc` is `Any?`. Glide handles standard types out-of-the-box (URLs, URIs, resource IDs, `File`). A `ModelResolver` sits in front of Glide and can rewrite the source into a different representation.

### Resolution Chain & Precedence

When resolving a model, resolvers run in this order:
1. **Per-view resolvers:** `image.modelResolvers`
2. **Global resolvers:** `GlideImageViewConfig.modelResolvers`
3. **Default resolver:** `DefaultModelResolver` (handles known URI schemes, `@drawable/...` string identifiers, `/sdcard/...` file paths, and relative asset paths `images/...`)

The first resolver to return a non-null value wins. If all custom resolvers return `null`, the request falls through to `DefaultModelResolver`.

### Recipe: Domain Model Resolver

Map your own business objects or domain models directly to image URLs:

```kotlin
data class Avatar(val userId: Int, val sizePx: Int = 200)

object AvatarResolver : ModelResolver {
    override fun resolve(context: Context, source: Any): Any? {
        if (source !is Avatar) return null
        return "https://picsum.photos/seed/user-${source.userId}/${source.sizePx}/${source.sizePx}"
    }
}

// Register globally in Application.onCreate()
GlideImageViewConfig.modelResolvers += AvatarResolver

// Use anywhere in your app:
imageView.load(Avatar(userId = 42))
```

### Recipe: Authenticated Endpoints (Bearer Token)

Attach custom authorization headers dynamically using Glide's `GlideUrl` and `LazyHeaders`:

```kotlin
class AuthHeaderResolver(
    private val tokenProvider: () -> String?
) : ModelResolver {
    override fun resolve(context: Context, source: Any): Any? {
        if (source !is String || !source.startsWith("http")) return null
        val token = tokenProvider() ?: return null
        
        return GlideUrl(
            source,
            LazyHeaders.Builder()
                .addHeader("Authorization", "Bearer $token")
                .addHeader("X-Client", "GlideImageView")
                .build()
        )
    }
}

// Per-view registration
imageView.modelResolvers += AuthHeaderResolver { userSession.token }

// Or app-wide registration
GlideImageViewConfig.modelResolvers += AuthHeaderResolver { userSession.token }
```

---

## 2. `Shape` — Composable Bitmap Transformations

Rather than relying on single boolean flags, `GlideImageView` models shapes as a `List<Shape>` (`com.genesys.glideimageview.Shape`). Shapes compose sequentially.

```kotlin
interface Shape {
    val appliesScaleType: Boolean get() = true
    fun transformation(view: ImageView): Transformation<Bitmap>?
}
```

### Understanding `appliesScaleType`

- **`true` (default):** Indicates a **mask** or geometric boundary (e.g., circle crop, rounded corners, squircles). The view's `ScaleType` (such as `centerCrop`) must be applied *before* the shape is cut out so the image fills the frame properly.
- **`false`:** Indicates an **effect** or filter (e.g., grayscale, blur, color matrix) that does not depend on view bounds.

### Built-in Shapes

- `Shape.Original` — No extra shape applied (respects `ScaleType`).
- `Shape.Circle` — Circular mask crop (`CircleCrop`).
- `Shape.RoundedCorners(radiusPx: Int)` — Crops the bitmap with corner radius in pixels.

### Recipe: Custom Squircle Shape

```kotlin
data class SquircleShape(val curvature: Float = 4f) : Shape {
    override fun transformation(view: ImageView): Transformation<Bitmap> =
        SquircleTransformation(curvature)
}
```

### Recipe: Border Shape

```kotlin
data class BorderShape(
    val widthPx: Float,
    val color: Int,
    val radiusPx: Float = 0f
) : Shape {
    override fun transformation(view: ImageView): Transformation<Bitmap> =
        BorderTransformation(widthPx, color, radiusPx)
}
```

### Recipe: Grayscale Filter (`appliesScaleType = false`)

```kotlin
object GrayscaleShape : Shape {
    private val transformation = GrayscaleTransformation()
    override val appliesScaleType: Boolean get() = false
    override fun transformation(view: ImageView): Transformation<Bitmap> = transformation
}
```

### Composing Multiple Shapes

Shapes run in the order defined:

```kotlin
val density = resources.displayMetrics.density

// Combines Squircle cut with a colored border
imageView.shapes = listOf(
    SquircleShape(curvature = 4f),
    BorderShape(widthPx = 3 * density, color = Color.BLUE)
)

// Wrap any standard Glide Transformation
imageView.shapes += Shape.of(BlurTransformation(12))
```

For unmanaged, raw Glide transformations without shape wrapping, pass them directly via `ImageOptions.transformations`.

---

## 3. `RequestDecorator` — Glide Request Escape Hatch

`ImageOptions` models common properties like placeholders, error drawables, and crossfade durations. For advanced Glide-specific request configurations, `RequestDecorator` serves as the escape hatch:

```kotlin
fun interface RequestDecorator {
    fun decorate(view: GlideImageView, request: RequestBuilder<Drawable>): RequestBuilder<Drawable>
}
```

### Execution Order

The request is built in one pass and **the last write wins**:

1. **`ImageOptions`** — placeholder, error, transformations, transition, signature, cache strategy.
2. **Global decorators:** `GlideImageViewConfig.decorators`.
3. **Per-view decorators:** `image.decorators`.

A decorator always overrides `ImageOptions`. Decorators are the escape hatch, while app-wide *defaults* belong in `GlideImageViewConfig.defaults`.

### Recipe: Cache Strategy & Exact Dimensions

```kotlin
val DiskCacheDecorator = RequestDecorator { _, request ->
    request.diskCacheStrategy(DiskCacheStrategy.ALL)
}

val ExactSizeDecorator = RequestDecorator { view, request ->
    if (view.width > 0 && view.height > 0) {
        request.override(view.width, view.height)
    } else {
        request
    }
}
```

### Recipe: Progressive Thumbnail Loading

```kotlin
fun thumbnailDecorator(scale: Float = 0.1f) = RequestDecorator { _, request ->
    request.thumbnail(request.clone().sizeMultiplier(scale).listener(null))
}
```

### Recipe: Request Priority

```kotlin
fun priorityDecorator(priority: Priority) = RequestDecorator { _, request ->
    request.priority(priority)
}

// Attach to critical hero image
heroImageView.decorators += priorityDecorator(Priority.HIGH)
```

---

## 4. `RequestManagerFactory` — Custom Glide Lifecycles

By default, `GlideImageView` resolves the Glide `RequestManager` via `Glide.with(context)`. If you need custom lifecycle tracking (such as attaching to `applicationContext` to survive fragment detach, or injecting a test double):

```kotlin
// Per-view
imageView.requestManagerFactory = RequestManagerFactory { view ->
    Glide.with(view.context.applicationContext)
}

// App-wide
GlideImageViewConfig.requestManagerFactory = RequestManagerFactory { view ->
    Glide.with(view.context.applicationContext)
}
```

---

## 5. `OnLoadListener` — Callbacks & Telemetry

Monitor request lifecycle events for individual views or across the entire application:

```kotlin
interface OnLoadListener {
    fun onLoadStarted(view: GlideImageView) {}
    fun onResourceReady(view: GlideImageView, resource: Drawable, dataSource: DataSource) {}
    fun onLoadFailed(view: GlideImageView, error: GlideException?) {}
    fun onCleared(view: GlideImageView) {}
}
```

- `onLoadStarted` fires when the request is submitted, before cache lookup, ensuring loading indicators are triggered accurately without guesswork.
- The originating `view` is passed into every callback, allowing a single listener instance to monitor multiple views.

### Per-View Kotlin DSL

```kotlin
val listener = imageView.addOnLoadListener(
    onReady = { view, drawable ->
        // Handle success
    },
    onFailed = { view, error ->
        // Handle failure
    }
)

// Remove listener when done
imageView.removeOnLoadListener(listener)
```

### App-Wide Telemetry & Performance Tracking

Add a listener to `GlideImageViewConfig.listeners` to capture metrics across all loads:

```kotlin
object LoadStats : OnLoadListener {
    override fun onLoadFailed(view: GlideImageView, error: GlideException?) {
        Analytics.trackImageFailure(error?.message)
    }
    
    override fun onResourceReady(view: GlideImageView, resource: Drawable, dataSource: DataSource) {
        Analytics.trackImageSuccess(dataSource = dataSource.name)
    }
}

// Register in Application.onCreate()
GlideImageViewConfig.listeners += LoadStats
```

---

## 6. Subclassing

While composable seams (`ModelResolver`, `Shape`, `RequestDecorator`) are recommended because they apply across existing layout files without subclass coupling, `GlideImageView` provides `protected open` methods if view inheritance is needed:

| Method | Responsibility |
|---|---|
| `resolveModel(source: Any?): Any?` | Custom model resolution step |
| `buildRequest(request: RequestBuilder<Drawable>, model: Any?): RequestBuilder<Drawable>` | Request building and option wiring |
| `isLocalResource(model: Any?): Boolean` | Which models bypass the cache when no strategy is set |
| `buildTransformations(): List<Transformation<Bitmap>>` | Transformation assembly |
| `scaleTypeTransformation(): Transformation<Bitmap>?` | ScaleType conversion for shapes |
| `renderPreview(model: Any)` | Edit-mode design-time preview rendering |
| `requestManager(): RequestManager` | Lifecycle-bound `RequestManager` lookup |
