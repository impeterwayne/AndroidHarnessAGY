---
trigger: always_on
---

# Android Workspace Rule: XML Views, ShapeView & Glide

This project's UI is **Android Views with XML layouts**. There is no Compose here.
This rule replaces `.agents/rules/android.md`; the two are never installed together.

## 1. Architecture

- Clean Architecture holds: `feature/*` → `core/domain` → `core/data`. UI never reaches
  past its ViewModel.
- Screens are `BaseActivity<VB>` / `BaseFragment<VB>` subclasses over **ViewBinding**.
  The binding is `mBinding`; the lifecycle work is already done in the base class, so a
  screen only fills `initViews()`, `onResizeViews()`, `onClickViews()`, `observeData()`.
- State holders are `@HiltViewModel` over a `BaseViewModel<Action, SideEffect>`: a
  `StateFlow` for state, a `Channel`/`SharedFlow` for one-shot side effects, and a
  `sealed interface <Screen>Action` / `<Screen>SideEffect` pair in `<Screen>Contract.kt`.
  Views send actions in; they never mutate state themselves.
- Collect on the view side with `repeatOnLifecycle(Lifecycle.State.STARTED)` — never a
  bare `lifecycleScope.launch` around a `collect`.
- Every `RecyclerView` is driven by an **Epoxy controller** (`TypedEpoxyController`,
  `PagingDataEpoxyController`) with `@EpoxyModelClass` rows over
  `BaseEpoxyViewBindingHolder<VB>`. No hand-written `RecyclerView.Adapter`, no
  `ListAdapter`, no `notifyDataSetChanged`.
- Preserve existing ViewModels, UseCases, Epoxy controllers and navigation contracts when
  restyling. A visual change that rewrites behaviour is a failed change.
- Never add comments in Kotlin code (`//`, `/* */`). KDoc on public API only.
- Never hardcode user-facing strings — `res/values/strings.xml`, then `@string/…` in the
  layout or `getString(...)` in code. Every `ImageView` that carries meaning gets an
  `android:contentDescription` from a `cd_*` string.

## 2. ShapeView is the background API — not `res/drawable`

`com.github.impeterwayne:ShapeView` (`com.genesys.shape.*`) is the **first** thing to
reach for when an element has a corner radius, a border, a fill, a gradient, a state
colour, a ripple or a shadow.

- Use `com.genesys.shape.layout.Shape{Linear,Frame,Relative,Constraint}Layout`,
  `ShapeRecyclerView`, `ShapeRadioGroup` and
  `com.genesys.shape.view.Shape{View,TextView,Button,ImageView,EditText,CheckBox,RadioButton}`
  in place of the plain widget, and set `app:shape_*` attributes inline.
- **Do not create a new `res/drawable/bg_*.xml` `<shape>`, `<selector>` or `<ripple>`.**
  That file is the thing this library exists to delete. Reuse an existing drawable if one
  already matches; otherwise express it with `shape_*`.
- State colours are attributes, not selectors: `shape_solidPressedColor`,
  `shape_solidSelectedColor`, `shape_solidDisabledColor`, `shape_strokeCheckedColor`,
  `shape_textSelectedColor`, and so on.
- Shadows are `shape_effect1Type="dropShadow"` + `Color`/`Blur`/`Spread`/`OffsetX`/`OffsetY`,
  up to four stacked slots — not a nine-patch and not `android:elevation` when the design
  gives a blur and an offset.
- Changing a shape at runtime goes through the Kotlin builders
  (`shapeDrawableBuilder … .intoBackground()`, `textColorBuilder … .intoTextColor()`),
  never by swapping a drawable resource. Builder values are **pixels**, XML values are dp.
- The exception, and the only one: a drawable that is genuinely a *drawing* — a vector
  icon, a layer-list, an animated selector — still belongs in `res/drawable`.

Details and recipes: skill `shape-view`.

## 3. Glide is the image API

- Remote URLs, asset paths, file paths, `Uri`s and byte arrays load through **Glide**
  (`com.github.bumptech.glide`) — never `setImageBitmap` off a manual decode, never a
  second loader alongside it.
- **`GlideImageView` (`com.github.impeterwayne:GlideImageView`, `com.genesys.glideimageview.GlideImageView`) is the image view**:
  use declarative `app:glideSrc` (`@drawable/...`, `images/...`, or remote URL),
  `app:glidePlaceholder`, `app:glideError`, `app:glideRadius`, `app:glideCircle`,
  `app:glideCrossFade`, `app:glideCacheType`, and `app:glideSkipMemoryCache` so the layout states
  what it loads. Asset paths and drawables render live in Android Studio Layout Editor preview.
- Where programmatic loading is needed, use `view.load(...)`, `view.loadAsset(...)`, or
  `view.clear()` rather than open-coding `Glide.with(...)` chains. For existing plain `ImageView`s,
  use the `ImageView.loadImage(...)` extension.
- Every load declares a `placeholder` and an `error`. A load with neither is a blank box
  on a slow network.
- In an Epoxy item model, load in `bind()` (`imgThumb.load(...)`) and clear in `unbind()`
  (`imgThumb.clear()`). An uncleared request writes the previous row's image into a recycled holder.
- Corner radii on a loaded image come from `app:glideRadius` / `app:glideCircle` (or Glide's
  `RoundedCorners`/`CircleCrop`), or from a `ShapeImageView` around it — never from a hand-cut PNG.

Details: skill `image-loading-glide`.

## 4. Design tokens live in `res/values`

- Colours: `@color/*` in `core/ui/res/values/colors.xml` (and `values-night`). **No raw
  `#RRGGBB` in a layout** outside the colour resource files themselves.
- Type: `TextAppearance.App.*` styles applied with `android:textAppearance`, not a loose
  `textSize` + `fontFamily` pair repeated per screen.
- Spacing: repeated values as `@dimen/*`; a genuinely one-off `16dp` may stay inline.
- Icons: `res/drawable/ic_<name>.xml` vectors, referenced as `app:srcCompat`.
- Layouts use `start`/`end`, never `left`/`right`.

## 5. Device & Build Ownership
- **Gradle never installs**: no `installDebug`, `connectedAndroidTest`, or any
  `install*`/`uninstall*`/`connected*` task. They pick a device themselves and overwrite
  whatever another git worktree is verifying on it. Assemble, then
  `andrun install --no-build --launch --json`.
- **Never `adb install`**: same reason. `andrun` resolves the device this worktree leased.
- **Never pass a device or serial**: the `device-gate` hook leases one on your first
  device command and injects `-s <serial>` into `scrcpy-cli` and `adb` for you. If it
  denies because every device is leased elsewhere, queue with
  `andrun queue ensure --wait-timeout 600 --json` — do not work around it.
