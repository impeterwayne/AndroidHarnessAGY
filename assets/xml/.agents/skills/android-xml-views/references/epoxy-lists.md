# Lists with Epoxy

Every `RecyclerView` on this track is driven by an **Epoxy controller**. Not a hand-written
`RecyclerView.Adapter`, and not a `ListAdapter` — a controller declares what the list
contains, Epoxy diffs it and does the rest.

The reason it is the house standard: a screen with a header, a body list, an inline ad
slot, an empty state and a footer is one `buildModels` block, where the adapter version is
four view types, a `getItemViewType` `when`, and a position-arithmetic bug.

## Setup

```toml
epoxy = "5.2.1"
epoxy = { module = "com.airbnb.android:epoxy", version.ref = "epoxy" }
epoxyProcessor = { module = "com.airbnb.android:epoxy-processor", version.ref = "epoxy" }
epoxyPaging3 = { module = "com.airbnb.android:epoxy-paging3", version.ref = "epoxy" }
```

```kotlin
plugins { alias(libs.plugins.ksp) }

dependencies {
    implementation(libs.epoxy)
    ksp(libs.epoxyProcessor)
    implementation(libs.epoxyPaging3)
}
```

The processor is what generates the `…Model_` classes. Without `ksp(libs.epoxyProcessor)`
in **that** module, `DocumentItemModel_` does not exist and every reference to it is an
unresolved symbol — the most common first failure when adding Epoxy to a new module.

## The item model

```kotlin
@EpoxyModelClass
abstract class DocumentItemModel :
    BaseEpoxyViewBindingHolder<ItemDocumentBinding>(ItemDocumentBinding::bind) {

    @EpoxyAttribute
    open var document: DocumentModel? = null

    @EpoxyAttribute
    open var position: Int = 0

    @EpoxyAttribute(EpoxyAttribute.Option.DoNotHash)
    open var onClickDocument: ((DocumentModel, Int) -> Unit)? = null

    @EpoxyAttribute(EpoxyAttribute.Option.DoNotHash)
    open var onClickMenu: ((DocumentModel, Int) -> Unit)? = null

    override fun getDefaultLayout(): Int = R.layout.item_document

    override fun ItemDocumentBinding.bind() {
        val data = document ?: return
        tvName.text = data.name
        tvSize.text = data.readableSize
        imgThumb.load(data.thumbnailUrl)
        root.isSelected = data.isSelected

        root.clickView { onClickDocument?.invoke(data, position) }
        ivMore.clickView { onClickMenu?.invoke(data, position) }
    }

    override fun ItemDocumentBinding.unbind() {
        root.setOnClickListener(null)
        ivMore.setOnClickListener(null)
        imgThumb.clear()
    }
}
```

Five rules, and four of them are about `@EpoxyAttribute`:

1. **Class is `abstract`, properties are `open var`, annotated `@EpoxyAttribute`.** The
   processor generates the concrete `DocumentItemModel_` by overriding them. A `val`, a
   `private`, or a missing `open` and the generated class will not compile.
2. **Lambdas take `EpoxyAttribute.Option.DoNotHash`.** Attributes feed the model's
   `hashCode`, which is what Epoxy diffs on. A lambda allocated fresh in every
   `buildModels` hashes differently every time, so without `DoNotHash` every row rebinds
   on every build and the list flickers and drops frames.
3. **Everything the bind reads must be an attribute.** A value pulled from a field, a
   singleton or a captured variable is invisible to the diff, so the row will not update
   when it changes.
4. **`unbind()` releases everything `bind()` attached.** Click listeners to `null`, Glide
   cleared, animations cancelled, observers removed. Epoxy reuses holders; a listener left
   behind fires against the previous row's data.
5. Attribute types must have a correct `equals`/`hashCode` — `data class` models, not
   plain classes.

`BaseEpoxyViewBindingHolder<VB>(VB::bind)` is the project's ViewBinding bridge over
`EpoxyModelWithHolder`; it gives `bind()`/`unbind()` as extension functions on the typed
binding. Use it rather than `EpoxyModelWithHolder` directly.

## The controller

```kotlin
class DocumentEpoxyController(
    private val onClickDocument: (DocumentModel, Int) -> Unit,
    private val onClickMenu: (DocumentModel, Int) -> Unit
) : TypedEpoxyController<DocumentUiState>() {

    override fun buildModels(state: DocumentUiState) {
        if (state.documents.isEmpty()) {
            emptyStateView { id("empty") }
            return
        }

        state.documents.forEachIndexed { index, item ->
            DocumentItemModel_()
                .id(item.id)
                .document(item)
                .position(index)
                .onClickDocument(onClickDocument)
                .onClickMenu(onClickMenu)
                .addTo(this)
        }

        if (state.isLoadingMore) {
            loadingRow { id("loading_footer") }
        }
    }
}
```

Wired up once in `initViews()`, fed from `render(state)`:

```kotlin
override fun initViews() {
    controller = DocumentEpoxyController(
        onClickDocument = { doc, pos -> viewModel.dispatch(DocumentAction.ClickDocument(doc)) },
        onClickMenu = { doc, pos -> viewModel.dispatch(DocumentAction.ClickMenu(doc, pos)) }
    )
    mBinding.listDocuments.setController(controller)
    mBinding.listDocuments.layoutManager = LinearLayoutManager(requireContext())
}

private fun render(state: DocumentUiState) {
    controller.setData(state)
}
```

`setData` on a `TypedEpoxyController` requests a model rebuild. With a plain
`EpoxyController` holding its own fields, call `requestModelBuild()` after setting them —
mutating a field without it changes nothing on screen.

## Ids are identity

`.id(...)` is what Epoxy diffs on, and it is not optional — a model without one throws at
build time.

- **Stable and unique**, from the domain: a database id, a file path, a URL. Never the
  list index, which reorders the whole list on a sort.
- **String ids for static rows**: `id("header")`, `id("empty")`, `id("loading_footer")`.
- **Two models with the same id in one build** is a crash. Where duplicates are genuinely
  possible from data, `setFilterDuplicates(true)` on the controller downgrades it to a
  logged warning — reach for it only when you have confirmed the source can legitimately
  repeat.

## Paged lists

```kotlin
class DocumentEpoxyController(
    private val onClickDocument: (DocumentModel, Int) -> Unit
) : PagingDataEpoxyController<DocumentModel>(itemDiffCallback = DIFF) {

    override fun buildItemModel(currentPosition: Int, item: DocumentModel?): EpoxyModel<*> =
        if (item == null) {
            DocumentItemModel_()
                .id("placeholder_$currentPosition")
                .document(null)
        } else {
            DocumentItemModel_()
                .id(item.id)
                .document(item)
                .position(currentPosition)
                .onClickDocument(onClickDocument)
        }

    private companion object {
        val DIFF = object : DiffUtil.ItemCallback<DocumentModel>() {
            override fun areItemsTheSame(old: DocumentModel, new: DocumentModel) =
                old.id == new.id

            override fun areContentsTheSame(old: DocumentModel, new: DocumentModel) =
                old == new
        }
    }
}
```

Fed with `controller.submitData(lifecycle, pagingData)`. `item` is nullable because
placeholders are on — `buildItemModel` must return a model for the null case too, with an
id derived from the position, and the item model's `bind()` must tolerate a null
attribute (`val data = document ?: return`).

Empty and error states for a paged list come from `loadStateFlow`, not from a field in
`UiState`.

Where the project instead paginates by scroll offset, `RecyclerViewPaginator` in
`core/ui/base/epoxy` wraps the scroll listener — use it rather than writing another one.

## Carousels and nested lists

A horizontal list inside a vertical one is Epoxy's `carousel`:

```kotlin
carousel {
    id("recent")
    numViewsToShowOnScreen(3.5f)
    models(state.recent.map { RecentItemModel_().id(it.id).item(it) })
}
```

This shares one recycled-view pool across carousels, which a nested `RecyclerView` does
not. Do not hand-roll it.

## Performance

- `EpoxyRecyclerView` in the layout rather than a plain `RecyclerView` — it sets up the
  shared pool and cleans up the controller for you.
- `buildModels` runs on every `setData`. Keep it to model construction: no formatting, no
  sorting, no file IO. Those belong in the ViewModel, computed once into the state the
  controller reads.
- Diffing is automatic and incremental. Never call `notifyDataSetChanged`.
- `onModelBound` / `onModelUnbound` on the controller are for impression tracking, not for
  binding work.

## Do not mix

One screen uses Epoxy, or it does not. A `ListAdapter` alongside an Epoxy controller in
the same feature means two diffing strategies, two item-model conventions and two places
to look. When touching a screen that still has a hand-written adapter, leave it unless
converting it is the task.
