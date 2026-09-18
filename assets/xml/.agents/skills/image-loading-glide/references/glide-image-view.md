# `GlideImageView` and the loading extensions

Reference implementations. Adjust the package and the `R.styleable` name; keep the
structure. Both belong in the shared UI module (`core/ui`, or the app's `ui/` package in a
single-module project), declared once and reused — not copied per feature.

## `res/values/attrs.xml`

```xml
<declare-styleable name="GlideImageView">
    <attr name="glideSrc" format="string" />
    <attr name="glidePlaceholder" format="reference" />
    <attr name="glideError" format="reference" />
    <attr name="glideRadius" format="dimension" />
    <attr name="glideCircle" format="boolean" />
    <attr name="glideCrossFade" format="boolean" />
</declare-styleable>
```

## `GlideImageView.kt`

```kotlin
open class GlideImageView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : AppCompatImageView(context, attrs, defStyleAttr) {

    data class Options(
        @DrawableRes val placeholder: Int = NO_RESOURCE,
        @DrawableRes val error: Int = NO_RESOURCE,
        val cornerRadiusPx: Int = 0,
        val isCircle: Boolean = false,
        val crossFade: Boolean = false
    )

    var options: Options = Options()
        set(value) {
            if (field == value) return
            field = value
            reload()
        }

    var glideSrc: String? = null
        set(value) {
            if (field == value && drawable != null) return
            field = value
            if (value.isNullOrBlank()) clear() else reload()
        }

    init {
        context.withStyledAttributes(attrs, R.styleable.GlideImageView) {
            options = Options(
                placeholder = getResourceId(R.styleable.GlideImageView_glidePlaceholder, NO_RESOURCE),
                error = getResourceId(R.styleable.GlideImageView_glideError, NO_RESOURCE),
                cornerRadiusPx = getDimensionPixelSize(R.styleable.GlideImageView_glideRadius, 0),
                isCircle = getBoolean(R.styleable.GlideImageView_glideCircle, false),
                crossFade = getBoolean(R.styleable.GlideImageView_glideCrossFade, false)
            )
            getString(R.styleable.GlideImageView_glideSrc)?.let { glideSrc = it }
        }
    }

    fun updateOptions(block: Options.() -> Options) {
        options = options.block()
    }

    fun reload() {
        val source = glideSrc
        if (source.isNullOrBlank()) return
        if (isInEditMode) {
            renderPreview(source)
            return
        }
        buildRequest(Glide.with(this).load(resolveModel(source))).into(this)
    }

    protected open fun buildRequest(request: RequestBuilder<Drawable>): RequestBuilder<Drawable> {
        var result = request
        if (options.placeholder != NO_RESOURCE) result = result.placeholder(options.placeholder)
        if (options.error != NO_RESOURCE) result = result.error(options.error)

        val transformations = transformations()
        result = when (transformations.size) {
            0 -> result
            1 -> result.transform(transformations.first())
            else -> result.transform(MultiTransformation(transformations))
        }

        return if (options.crossFade) {
            result.transition(DrawableTransitionOptions.withCrossFade())
        } else {
            result.dontAnimate()
        }
    }

    protected open fun transformations(): List<Transformation<Bitmap>> = when {
        options.isCircle -> listOf(CircleCrop())
        options.cornerRadiusPx > 0 -> listOfNotNull(
            scaleTransformation(),
            RoundedCorners(options.cornerRadiusPx)
        )
        else -> emptyList()
    }

    protected open fun resolveModel(source: String): Any =
        if (KNOWN_SCHEMES.any { source.startsWith(it, ignoreCase = true) }) source
        else assetUri(source)

    private fun clear() {
        if (!isInEditMode) Glide.with(this).clear(this)
        setImageDrawable(null)
    }

    private fun scaleTransformation(): Transformation<Bitmap>? = when (scaleType) {
        ScaleType.CENTER_CROP -> CenterCrop()
        ScaleType.FIT_CENTER, ScaleType.FIT_START, ScaleType.FIT_END -> FitCenter()
        ScaleType.CENTER_INSIDE -> CenterInside()
        else -> null
    }

    private fun renderPreview(source: String) {
        runCatching {
            context.assets.open(source.removePrefix(ASSET_SCHEME)).use {
                setImageBitmap(BitmapFactory.decodeStream(it))
            }
        }.onFailure {
            if (options.placeholder != NO_RESOURCE) setImageResource(options.placeholder)
        }
    }

    companion object {
        private const val NO_RESOURCE = 0
        private const val ASSET_SCHEME = "file:///android_asset/"
        private val KNOWN_SCHEMES =
            listOf("http://", "https://", "content://", "file://", "android.resource://")

        @JvmStatic
        fun assetUri(path: String): String = ASSET_SCHEME + path.trimStart('/')
    }
}
```

### Why it is shaped this way

- **`isInEditMode` branch.** Studio's layout preview has no Glide; without it every screen
  using this view renders empty in the editor and the layout cannot be judged at all.
- **`scaleTransformation()` paired with `RoundedCorners`.** `RoundedCorners` alone
  replaces the scaling Glide would otherwise apply, and the image distorts. This is the bug
  that makes people give up and ship pre-rounded PNGs.
- **`clear()` on a null or blank source.** Reassigning `glideSrc` cancels the in-flight
  request, so a recycled holder cannot receive the previous row's bitmap.
- **`options` as a data class with a `field == value` guard.** Binding the same item twice
  does not restart the load, which is what makes it safe to assign unconditionally from an
  Epoxy model's `bind()`, which runs on every model rebuild.
- **`open` + `protected`.** A feature that needs a blur or a cache signature subclasses and
  overrides `transformations()` or `buildRequest()` instead of forking the view.

## `ImageViewExt.kt`

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

`source` is `Any?` deliberately — Glide accepts a `String` URL, a `Uri`, a `File`, a
`ByteArray` and a `@DrawableRes Int`, and narrowing the parameter would force a cast at
every call site.

## Binding in an Epoxy item model — the whole pattern

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
        imgThumb.glideSrc = data.thumbnailUrl
    }

    override fun ItemDocumentBinding.unbind() {
        Glide.with(imgThumb).clear(imgThumb)
    }
}
```

With a plain `ImageView` the bind line becomes `imgThumb.loadImage(data.thumbnailUrl,
placeholder = R.drawable.ic_placeholder, error = R.drawable.ic_broken, radiusPx = radius)`.
The `unbind()` clear is required either way — Epoxy reuses holders, and an in-flight
request that completes after reuse paints the previous row's image.
