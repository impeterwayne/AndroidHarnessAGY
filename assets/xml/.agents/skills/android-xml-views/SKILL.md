---
name: android-xml-views
description: Use when building or changing screens in an Android View/XML project (no Compose) - ViewBinding over BaseActivity/BaseFragment, the Action/SideEffect contract with BaseViewModel and StateFlow, lifecycle-safe collection, Epoxy controllers and models for every RecyclerView, dialogs and bottom sheets, navigation, and the module layout of a multi-module XML app. The XML-track counterpart to the Compose architecture skills.
---

# Android XML view architecture

The project's UI is Views and XML layouts. This skill is the shape a screen takes here:
what file goes where, what the base classes already do for you, and the handful of
mistakes that account for most View-layer bugs.

Companion skills on this track: `shape-view` (backgrounds, corners, borders, shadows),
`image-loading-glide` (images), `xml-resource-policy` (strings, colours, dimens, styles),
`figma2xml` (design to layout).

## What a screen is made of

```
feature/<name>/
  <Name>Fragment.kt        BaseFragment<Fragment<Name>Binding> — views only
  <Name>ViewModel.kt       @HiltViewModel : BaseViewModel<Action, SideEffect>
  <Name>Contract.kt        sealed interface <Name>Action / <Name>SideEffect
  epoxy/<Name>EpoxyController.kt   TypedEpoxyController<UiState>
  epoxy/<Name>ItemModel.kt         @EpoxyModelClass over the row's ViewBinding
  res/layout/fragment_<name>.xml
  res/layout/item_<name>.xml
```

An Activity-hosted screen is the same with `BaseActivity<Activity<Name>Binding>`. Screens
with no list legitimately skip the `epoxy/` package; nothing else is optional, and a
ViewModel that would hold no state is a sign the screen is a dialog, not a screen.

## The base classes do the lifecycle

`BaseActivity<VB>` and `BaseFragment<VB>` take the generated binding's inflater as a
constructor argument, expose it as `mBinding`, and call four open functions in order —
`initViews` (controllers, layout managers, static setup), `onResizeViews` (insets and
measured-size work), `onClickViews` (listeners that dispatch actions), `observerData`
(collect state and side effects):

```kotlin
@AndroidEntryPoint
class DocumentFragment : BaseFragment<FragmentDocumentBinding>(FragmentDocumentBinding::inflate) {

    private val viewModel by viewModels<DocumentViewModel>()

    override fun initViews() { … }
    override fun onResizeViews() { … }
    override fun onClickViews() { … }
    override fun observerData() { … }
}
```

Do not override `onCreateView`, `onViewCreated` or `onCreate` to add work — the ordering
the base class guarantees is the point of it. Put the work in the hook that names it.

Full contract, including the immersive-bar and insets hooks:
[references/base-classes.md](./references/base-classes.md).

## State in, actions out

The ViewModel owns state. The Fragment renders it and sends actions. It never computes
state, never reaches past the ViewModel, and never holds a second copy of anything the
ViewModel already has.

```kotlin
sealed interface DocumentAction : IAction {
    data object Refresh : DocumentAction
    data class ClickDocument(val document: DocumentModel) : DocumentAction
    data class SortChanged(val sort: SortType, val order: OrderType) : DocumentAction
}

sealed interface DocumentSideEffect : ISideEffect {
    data class OpenViewer(val uri: Uri) : DocumentSideEffect
    data class ShowToast(val message: ToastMessage) : DocumentSideEffect
    data object ScrollToHead : DocumentSideEffect
}
```

The split is the whole discipline: **state is what the screen looks like, a side effect is
something that happens once.** Navigation, a toast, a sheet, a scroll — all side effects.
A `Boolean` in state that means "navigate now" is the bug this design exists to prevent,
because it fires again on rotation.

`ToastMessage` carries a `@StringRes Int` or a `String`, never a resolved string — a
ViewModel that formats user-facing text has taken a `Context` it should not have.

## Collecting is where lifecycle bugs live

```kotlin
override fun observerData() {
    viewLifecycleOwner.lifecycleScope.launch {
        viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            launch { viewModel.uiState.collect(::render) }
            launch { viewModel.sideEffect.collect(::handle) }
        }
    }
}
```

Three things that are always wrong here:

- `lifecycleScope.launch { flow.collect { } }` with no `repeatOnLifecycle` — the collector
  survives into the background and touches destroyed views.
- `lifecycleScope` instead of `viewLifecycleOwner.lifecycleScope` in a Fragment — the
  Fragment outlives its view, so the collector writes into a binding that is gone.
- Two sequential `collect` calls in one `launch` — the second never runs. Each gets its
  own `launch`.

Side effects come off a `Channel(Channel.BUFFERED).receiveAsFlow()` or a
`MutableSharedFlow(replay = 0)`. Never a `StateFlow` — a `StateFlow` replays its last
value to the next collector and the navigation fires twice.

## `render(state)` is a total function

One function that takes the whole state and sets every view it owns. Not a set of
listeners each poking one view.

```kotlin
private fun render(state: DocumentUiState) = with(mBinding) {
    progress.isVisible = state.isLoading
    emptyView.isVisible = state.isEmpty
    listDocuments.isVisible = state.documents.isNotEmpty()
    chipAll.isSelected = state.filter == Filter.ALL
    controller.setData(state)
}
```

Every branch sets every view it controls, including back to the default. A `render` that
only shows things leaves the previous state's spinner on screen.

Selection and enabled states go through `isSelected` / `isChecked` / `isEnabled` on a
`Shape*` view with the state colours declared in XML — not `setBackgroundResource` in the
bind. See `shape-view`.

For a screen whose body is a list, `render` is usually one line: `controller.setData(state)`.
Everything the rows show then lives in the state the controller receives.

## Lists are Epoxy

Every `RecyclerView` here is driven by an **Epoxy controller** — not a hand-written
`RecyclerView.Adapter` and not a `ListAdapter`. A controller declares what the list
contains; Epoxy diffs it.

```kotlin
override fun initViews() {
    controller = DocumentEpoxyController(
        onClickDocument = { doc, _ -> viewModel.dispatch(DocumentAction.ClickDocument(doc)) }
    )
    mBinding.listDocuments.setController(controller)
}

private fun render(state: DocumentUiState) {
    controller.setData(state)
}
```

Rows are `@EpoxyModelClass` models over `BaseEpoxyViewBindingHolder<ItemBinding>`, with
every value the bind reads declared as an `@EpoxyAttribute` and every lambda marked
`DoNotHash`. `notifyDataSetChanged` is not an update path here; neither is rebuilding the
controller on each emission.

Models, controllers, ids, paging, carousels, and the `unbind()` rule that keeps recycled
rows honest: [references/epoxy-lists.md](./references/epoxy-lists.md).

## Dialogs and bottom sheets

`BaseDialog<VB>` and `BaseBottomSheetDialogFragment<VB>` follow the same hook pattern.
A sheet is shown from a **side effect**, not from a click listener directly — that keeps
the "which sheet is open" decision in the ViewModel where the rest of the screen's logic
lives, and it survives rotation.

Results come back through a callback passed at construction or a
`setFragmentResultListener`; never through a mutable global.

## Navigation

Follow whatever the project already has, and check before assuming:

- **Activity-per-screen with a router** — `AppRouter.navigateTo(context, destination)`
  with a `ScreenDestination` sealed type, called from the side-effect handler. Feature
  modules depend on the destination type, not on each other's Activities.
- **Jetpack Navigation with fragments** — `findNavController().navigate(directions)` from
  the side-effect handler, `res/navigation/*.xml` graphs, Safe Args where set up.

Either way: the ViewModel emits "go here", the view layer performs it. A ViewModel holding
a `Context` or an `Intent` has crossed the line.

## Module structure

Multi-module projects here follow: `app` → `feature/*` → `core/ui`, `core/domain`,
`core/data`, `core/model`, `core/common`, with Gradle convention plugins in
`build-logic/convention` so a new feature module is five lines of build script.

Which module a file belongs in, and what a new feature module needs:
[references/module-structure.md](./references/module-structure.md).

A single-module app is a legitimate shape too — the same package layout under
`ui/base`, `ui/component/<screen>`, `ui/component/adapter`, `data`, `di`, `utils`. Do not
propose a modularisation nobody asked for.

## Non-negotiables

- **No Kotlin comments** (`//`, `/* */`). KDoc on public API only.
- **No hardcoded user-facing strings** — `@string/…` in the layout, `getString(...)` in
  code, plurals for counts, placeholders for formatting.
- **No raw hex in a layout** — `@color/…`. Colours are defined in `colors.xml` and
  nowhere else.
- **No new `<shape>` / `<selector>` / `<ripple>` drawable** — that is `shape-view`'s job.
- **`start`/`end`, never `left`/`right`.**
- **Every meaningful `ImageView` has a `contentDescription`**; decorative ones say `@null`
  explicitly.
- **Preserve existing ViewModels, adapters and navigation contracts** when restyling.
- **YAGNI** — no base class with one subclass, no interface with one implementation, no
  parameter for a variant that does not exist.

## Verification

A layout error is a resource-linking failure, not a Kotlin one, so
`compileDebugKotlin` will not catch a misspelled attribute or a missing `@string`.

- `./gradlew :<module>:assembleDebug` — the real check.
- Grep every `R.string`, `R.drawable`, `R.dimen`, `R.color` and binding id you introduced.
  A binding field only exists if the layout's `android:id` matches exactly, and a typo
  there compiles fine in XML and fails in Kotlin with an unhelpful message.
- Generated Epoxy classes (`…Model_`) only exist if `ksp(libs.epoxyProcessor)` is on
  **that** module. An unresolved `DocumentItemModel_` is a missing processor, not a typo.
- For UI-facing work, the screen has to be driven on a device. A green build says nothing
  about whether a `ConstraintLayout` chain collapsed.
