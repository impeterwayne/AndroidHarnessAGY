# Custom Bottom Navigation View Reference Implementation

> **Rule: Create a custom bottom navigation view (`CustomBottomNavigationView`) instead of using the default Material `BottomNavigationView`.**

---

## 1. Why Create Custom Instead of Default `BottomNavigationView`

Material Components' default `com.google.android.material.bottomnavigation.BottomNavigationView` is inadequate for modern, pixel-precise custom mobile designs:

| Requirement | Material `BottomNavigationView` | `CustomBottomNavigationView` (Custom) |
| :--- | :--- | :--- |
| **Top-Pinned Active Indicator** | Fails. Material 3 active indicator is an oval pill centered on the icon. Panning or pinning it to the top edge requires fragile reflection or custom drawables. | Native. `indicatorView` is an explicit rounded bar (`52dp × 3dp`, `2dp` radius) pinned directly to the top edge (`y = 0`). |
| **Upward Soft Drop Shadow** | Fails. Android elevation only casts downward and clips against parent bounds. | Native. Uses `Paint.setShadowLayer` with `LAYER_TYPE_SOFTWARE` and reserved `6dp` top margin for smooth upward blur (`-2dp` offset, `4dp` blur). |
| **Hairline Top Divider** | Fails or requires nested views / custom shape drawables. | Native. Canvas draws a clean 1dp line (`canvas.drawLine`) along the top boundary. |
| **Equal Tab Partitioning** | Uses internal auto-layout calculations that can cause 1px rounding gaps on high-density displays. | Exact integer division `(i * width) / count` in `onMeasure`/`onLayout`. |
| **State Synchronization** | Inflexible item bindings. | Native `isDuplicateParentStateEnabled = true` on child `ImageView` and `TextView`. Setting `isSelected` on the item automatically swaps icon drawables and text colors. |
| **Dependencies** | Requires `com.google.android.material`. | Zero additional dependencies. Pure Android SDK `FrameLayout`, `Canvas`, and `Paint`. |

---

## 2. Visual Architecture & Design Specifications

```
┌───────────────────────────────────────────────────────────┐
│ ^^^^^^^^^^^^^^^^^ 6dp Shadow Area ^^^^^^^^^^^^^^^^^^^^^^^ │
├───────────────────────────────────────────────────────────┤ <- 1dp Divider Line
│   [======] Indicator (52x3dp, r=2dp)                      │
│      /\                                                   │
│     /  \   Icon (24x24dp)                                 │
│    /____\                                                 │
│     Files  Text (12sp, Mulish Medium)                     │
│                                                           │
│   Tab 1 (Active)       Tab 2            Tab 3     Tab 4   │
└───────────────────────────────────────────────────────────┘
```

| Constant | Value | Role |
| :--- | :--- | :--- |
| `SHADOW_HEIGHT_DP` | `6dp` | Vertical buffer reserved above items for the upward drop shadow |
| `SHADOW_COLOR` | `#1A000000` (10% black) | Upward ambient shadow color |
| `SHADOW_SIZE_DP` | `4dp` | Shadow blur radius |
| `SHADOW_OFFSET_Y_DP` | `-2dp` | Upward shadow translation |
| `INDICATOR_WIDTH_DP` | `52dp` | Top indicator bar width |
| `INDICATOR_HEIGHT_DP`| `3dp` | Top indicator bar thickness |
| `INDICATOR_RADIUS_DP`| `2dp` | Top indicator corner radius |
| `ICON_SIZE_DP` | `24dp` | Tab icon dimensions |
| `TEXT_SIZE_SP` | `12sp` | Tab text size |
| `ITEM_TEXT_TOP_MARGIN_DP` | `3dp` | Gap between icon and label |
| `BAR_HEIGHT_DP` | `72dp` – `78dp` | Standard bar height |

---

## 3. Production Implementation (`CustomBottomNavigationView.kt`)

Drop this into your shared UI module (e.g., `core/ui/custom/CustomBottomNavigationView.kt`):

```kotlin
package your.app.package.core.ui.custom

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.drawable.GradientDrawable
import android.util.AttributeSet
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.TextView
import androidx.annotation.DrawableRes
import androidx.annotation.StringRes
import androidx.core.content.ContextCompat
import androidx.core.content.res.ResourcesCompat
import your.app.package.core.ui.R as UiR
import java.util.LinkedHashMap

/**
 * Custom bottom navigation view featuring an upward soft drop shadow,
 * a hairline top divider, and a top-pinned active indicator bar.
 */
class CustomBottomNavigationView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : FrameLayout(context, attrs, defStyleAttr) {

    /**
     * Callback triggered when a tab is clicked.
     */
    var onItemClickListener: ((ItemId) -> Unit)? = null

    /**
     * Callback triggered when the currently active tab is clicked again.
     */
    var onItemReselectedListener: ((ItemId) -> Unit)? = null

    /**
     * Tab identifiers matching app destinations.
     */
    enum class ItemId {
        FILES, RECENTS, FAVORITE, UTILITIES
    }

    private val items = LinkedHashMap<ItemId, NavigationItemView>()
    private val itemImages = LinkedHashMap<ItemId, ImageView>()
    private val itemTexts = LinkedHashMap<ItemId, TextView>()

    private var currentSelectedId: ItemId = ItemId.FILES

    private val bgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = ContextCompat.getColor(context, UiR.color.color_bg_main)
        style = Paint.Style.FILL
    }

    private val dividerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = ContextCompat.getColor(context, UiR.color.color_surface_container_highest)
        strokeWidth = 1.dp.toFloat()
        style = Paint.Style.STROKE
    }

    private val path = Path()

    private val Int.dp: Int
        get() = (this * resources.displayMetrics.density).toInt()

    private val Float.dp: Float
        get() = this * resources.displayMetrics.density

    private val shadowHeight: Int
        get() = SHADOW_HEIGHT_DP.dp

    init {
        setWillNotDraw(false)

        bgPaint.setShadowLayer(
            SHADOW_SIZE_DP.dp,
            SHADOW_OFFSET_X_DP.dp,
            SHADOW_OFFSET_Y_DP.dp,
            SHADOW_COLOR
        )
        setLayerType(View.LAYER_TYPE_SOFTWARE, null)

        addItem(ItemId.FILES, UiR.drawable.selector_nav_home, UiR.string.txt_files)
        addItem(ItemId.RECENTS, UiR.drawable.selector_nav_recent, UiR.string.txt_recents)
        addItem(ItemId.FAVORITE, UiR.drawable.selector_nav_bookmark, UiR.string.txt_favorite)
        addItem(ItemId.UTILITIES, UiR.drawable.selector_nav_tools, UiR.string.txt_utilities)

        selectItem(ItemId.FILES)
    }

    private fun addItem(
        itemId: ItemId,
        @DrawableRes iconRes: Int,
        @StringRes textRes: Int
    ) {
        val imageView = ImageView(context).apply {
            val size = ICON_SIZE_DP.dp
            layoutParams = LayoutParams(size, size)
            setImageResource(iconRes)
            isDuplicateParentStateEnabled = true
        }

        val textView = TextView(context).apply {
            gravity = Gravity.CENTER
            setText(textRes)
            textSize = TEXT_SIZE_SP

            try {
                typeface = ResourcesCompat.getFont(context, UiR.font.mulish_medium)
            } catch (ignored: Exception) {
            }

            setTextColor(ContextCompat.getColorStateList(context, UiR.color.selector_nav_text))
            isDuplicateParentStateEnabled = true
        }

        val itemView = NavigationItemView(context, itemId, imageView, textView).apply {
            setOnClickListener {
                if (currentSelectedId == itemId) {
                    onItemReselectedListener?.invoke(itemId)
                } else {
                    selectItem(itemId)
                    onItemClickListener?.invoke(itemId)
                }
            }
        }

        addView(itemView)

        items[itemId] = itemView
        itemImages[itemId] = imageView
        itemTexts[itemId] = textView
    }

    /**
     * Selects a tab and synchronizes state across child items.
     */
    fun selectItem(itemId: ItemId) {
        currentSelectedId = itemId
        items.forEach { (id, view) ->
            view.isSelected = (id == itemId)
        }
    }

    /**
     * Returns the currently selected item.
     */
    fun getSelectedItem(): ItemId = currentSelectedId

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        path.reset()
        path.addRect(
            0f,
            shadowHeight.toFloat(),
            w.toFloat(),
            h.toFloat(),
            Path.Direction.CW
        )
    }

    override fun onDraw(canvas: Canvas) {
        canvas.drawPath(path, bgPaint)
        val topY = (paddingTop + shadowHeight).toFloat()
        canvas.drawLine(0f, topY, width.toFloat(), topY, dividerPaint)
        super.onDraw(canvas)
    }

    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val widthSize = MeasureSpec.getSize(widthMeasureSpec)
        val heightMode = MeasureSpec.getMode(heightMeasureSpec)
        val heightSize = MeasureSpec.getSize(heightMeasureSpec)
        val count = childCount

        val targetChildHeight = if (heightMode == MeasureSpec.EXACTLY) {
            maxOf(0, heightSize - paddingTop - paddingBottom - shadowHeight)
        } else {
            0
        }

        var maxChildHeight = 0
        if (count > 0) {
            for (i in 0 until count) {
                val child = getChildAt(i)
                if (child.visibility != GONE) {
                    val left = (i * widthSize) / count
                    val right = ((i + 1) * widthSize) / count
                    val childWidth = right - left
                    val childWidthSpec = MeasureSpec.makeMeasureSpec(childWidth, MeasureSpec.EXACTLY)
                    val childHeightSpec = if (heightMode == MeasureSpec.EXACTLY) {
                        MeasureSpec.makeMeasureSpec(targetChildHeight, MeasureSpec.EXACTLY)
                    } else {
                        MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED)
                    }
                    child.measure(childWidthSpec, childHeightSpec)
                    maxChildHeight = maxOf(maxChildHeight, child.measuredHeight)
                }
            }
        }

        val totalHeight = if (heightMode == MeasureSpec.EXACTLY) {
            heightSize
        } else {
            maxChildHeight + paddingTop + paddingBottom + shadowHeight
        }

        setMeasuredDimension(
            resolveSizeAndState(widthSize, widthMeasureSpec, 0),
            resolveSizeAndState(totalHeight, heightMeasureSpec, 0)
        )
    }

    override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
        val count = childCount
        if (count == 0) return

        val parentWidth = r - l
        val parentHeight = b - t
        val childTop = paddingTop + shadowHeight
        val childBottom = parentHeight - paddingBottom

        for (i in 0 until count) {
            val child = getChildAt(i)
            if (child.visibility != GONE) {
                val left = (i * parentWidth) / count
                val right = ((i + 1) * parentWidth) / count
                child.layout(left, childTop, right, childBottom)
            }
        }
    }

    private class NavigationItemView(
        context: Context,
        val itemId: ItemId,
        val imageView: ImageView,
        val textView: TextView
    ) : FrameLayout(context) {

        private val Int.dp: Int
            get() = (this * resources.displayMetrics.density).toInt()

        val indicatorView = View(context).apply {
            val drawable = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = INDICATOR_RADIUS_DP * resources.displayMetrics.density
                setColor(ContextCompat.getColor(context, UiR.color.color_so_red))
            }
            background = drawable
            visibility = View.INVISIBLE
        }

        init {
            addView(indicatorView)
            addView(imageView)
            addView(textView)

            val outValue = TypedValue()
            context.theme.resolveAttribute(android.R.attr.selectableItemBackgroundBorderless, outValue, true)
            setBackgroundResource(outValue.resourceId)

            isClickable = true
            isFocusable = true
        }

        override fun setSelected(selected: Boolean) {
            super.setSelected(selected)
            indicatorView.visibility = if (selected) View.VISIBLE else View.INVISIBLE
        }

        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            val totalWidth = MeasureSpec.getSize(widthMeasureSpec)

            val indicatorWidth = minOf(INDICATOR_WIDTH_DP.dp, totalWidth)
            val indicatorHeight = INDICATOR_HEIGHT_DP.dp
            indicatorView.measure(
                MeasureSpec.makeMeasureSpec(indicatorWidth, MeasureSpec.EXACTLY),
                MeasureSpec.makeMeasureSpec(indicatorHeight, MeasureSpec.EXACTLY)
            )

            val imageSize = ICON_SIZE_DP.dp
            val imageWidthSpec = MeasureSpec.makeMeasureSpec(imageSize, MeasureSpec.EXACTLY)
            val imageHeightSpec = MeasureSpec.makeMeasureSpec(imageSize, MeasureSpec.EXACTLY)
            imageView.measure(imageWidthSpec, imageHeightSpec)

            val textWidthSpec = if (MeasureSpec.getMode(widthMeasureSpec) == MeasureSpec.UNSPECIFIED) {
                MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED)
            } else {
                MeasureSpec.makeMeasureSpec(totalWidth, MeasureSpec.AT_MOST)
            }
            val textHeightSpec = if (MeasureSpec.getMode(heightMeasureSpec) == MeasureSpec.UNSPECIFIED) {
                MeasureSpec.makeMeasureSpec(0, MeasureSpec.UNSPECIFIED)
            } else {
                MeasureSpec.makeMeasureSpec(MeasureSpec.getSize(heightMeasureSpec), MeasureSpec.AT_MOST)
            }
            textView.measure(textWidthSpec, textHeightSpec)

            val totalHeight = if (MeasureSpec.getMode(heightMeasureSpec) == MeasureSpec.EXACTLY) {
                MeasureSpec.getSize(heightMeasureSpec)
            } else {
                val paddingTop = ITEM_PADDING_TOP_DP.dp
                val paddingBottom = ITEM_PADDING_BOTTOM_DP.dp
                val textTopMargin = ITEM_TEXT_TOP_MARGIN_DP.dp
                paddingTop + imageSize + textTopMargin + textView.measuredHeight + paddingBottom + indicatorHeight
            }

            setMeasuredDimension(
                resolveSizeAndState(totalWidth, widthMeasureSpec, 0),
                resolveSizeAndState(totalHeight, heightMeasureSpec, 0)
            )
        }

        override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
            val width = r - l
            val height = b - t

            val indicatorWidth = indicatorView.measuredWidth
            val indicatorHeight = indicatorView.measuredHeight
            val indicatorLeft = (width - indicatorWidth) / 2
            indicatorView.layout(indicatorLeft, 0, indicatorLeft + indicatorWidth, indicatorHeight)

            val textMarginTop = ITEM_TEXT_TOP_MARGIN_DP.dp
            val contentHeight = imageView.measuredHeight + textMarginTop + textView.measuredHeight
            val availableHeight = height - indicatorHeight
            val contentTop = indicatorHeight + maxOf(0, (availableHeight - contentHeight) / 2)

            val imageLeft = (width - imageView.measuredWidth) / 2
            val imageTop = contentTop
            val imageRight = imageLeft + imageView.measuredWidth
            val imageBottom = imageTop + imageView.measuredHeight
            imageView.layout(imageLeft, imageTop, imageRight, imageBottom)

            val textLeft = (width - textView.measuredWidth) / 2
            val textTop = imageBottom + textMarginTop
            val textRight = textLeft + textView.measuredWidth
            val textBottom = textTop + textView.measuredHeight
            textView.layout(textLeft, textTop, textRight, textBottom)
        }
    }

    companion object {
        private const val SHADOW_COLOR = 0x1A000000
        private const val SHADOW_OFFSET_X_DP = 0f
        private const val SHADOW_OFFSET_Y_DP = -2f
        private const val SHADOW_SIZE_DP = 4f
        private const val SHADOW_HEIGHT_DP = 6

        private const val INDICATOR_WIDTH_DP = 52
        private const val INDICATOR_HEIGHT_DP = 3
        private const val INDICATOR_RADIUS_DP = 2f

        private const val ICON_SIZE_DP = 24
        private const val TEXT_SIZE_SP = 12f

        private const val ITEM_PADDING_TOP_DP = 10
        private const val ITEM_PADDING_BOTTOM_DP = 10
        private const val ITEM_TEXT_TOP_MARGIN_DP = 3
    }
}
```

---

## 4. State Selectors (`res/color` and `res/drawable`)

### Text Color Selector (`res/color/selector_nav_text.xml`)
```xml
<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_selected="true" android:color="@color/color_nav_active" />
    <item android:color="@color/color_nav_inactive" />
</selector>
```

### Icon Drawable Selector (`res/drawable/selector_nav_home.xml`)
```xml
<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_selected="true" android:drawable="@drawable/ic_home_active" />
    <item android:drawable="@drawable/ic_home_inactive" />
</selector>
```

Because `isDuplicateParentStateEnabled = true` is set on both `ImageView` and `TextView`, setting `view.isSelected = true` on the item automatically triggers `state_selected="true"` in both selectors.

---

## 5. Screen Integration (`res/layout/activity_main.xml`)

Place `CustomBottomNavigationView` inside a `FrameLayout` or directly pinned to bottom in `ConstraintLayout`:

```xml
<FrameLayout
    android:id="@+id/layout_bottom"
    android:layout_width="match_parent"
    android:layout_height="78dp"
    android:layout_alignParentBottom="true"
    app:layout_constraintBottom_toTopOf="@+id/fr_banner"
    app:layout_constraintStart_toStartOf="parent"
    app:layout_constraintEnd_toEndOf="parent">

    <your.app.package.core.ui.custom.CustomBottomNavigationView
        android:id="@+id/layout_menu_bottom"
        android:layout_width="match_parent"
        android:layout_height="match_parent" />
</FrameLayout>
```

---

## 6. Activity / Fragment Wiring (`MainActivity.kt`)

```kotlin
mBinding.layoutMenuBottom.onItemClickListener = { itemId ->
    when (itemId) {
        CustomBottomNavigationView.ItemId.FILES -> {
            if (currentFragment !is HomeFragment) {
                switchFragment(HomeFragment::class)
            }
        }
        CustomBottomNavigationView.ItemId.RECENTS -> {
            if (currentFragment !is RecentFragment) {
                switchFragment(RecentFragment::class)
            }
        }
        CustomBottomNavigationView.ItemId.FAVORITE -> {
            if (currentFragment !is FavoriteFragment) {
                switchFragment(FavoriteFragment::class)
            }
        }
        CustomBottomNavigationView.ItemId.UTILITIES -> {
            if (currentFragment !is ToolsFragment) {
                switchFragment(ToolsFragment::class)
            }
        }
    }
}
```

---

## 7. Dynamic Item Adaptation (For Generic Apps)

If tabs must be configured dynamically at runtime rather than via an enum:

```kotlin
data class BottomNavItem(
    val id: Int,
    @DrawableRes val iconRes: Int,
    @StringRes val titleRes: Int
)

fun setItems(navItems: List<BottomNavItem>, defaultSelectedId: Int = navItems.first().id) {
    removeAllViews()
    items.clear()
    itemImages.clear()
    itemTexts.clear()

    navItems.forEach { item ->
        addItem(item.id, item.iconRes, item.titleRes)
    }

    selectItem(defaultSelectedId)
}
```
