# Base classes, ViewBinding and the screen contract

Reference shapes. A project that already has these uses its own — read the real
`BaseActivity` / `BaseFragment` before writing a screen, because the hook names differ
between codebases (`observeData` vs `observerData` is a real difference that costs a
debugging round).

## `BaseActivity<VB>`

```kotlin
abstract class BaseActivity<VB : ViewBinding>(
    private val inflate: (LayoutInflater) -> VB
) : AppCompatActivity() {

    lateinit var mBinding: VB

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestWindow()
        mBinding = inflate(layoutInflater)
        setContentView(mBinding.root)
        setupWindowInsets()
        initImmersiveBar()
        initViews()
        onResizeViews()
        onClickViews()
        observeData()
    }

    open fun requestWindow() {}
    open fun initViews() {}
    open fun onResizeViews() {}
    open fun onClickViews() {}
    open fun observeData() {}

    protected open fun statusBarInsetTarget(): View? = null
    protected open fun isForceDarkMode(): Boolean = true
    protected open fun isFitsSystemWindows(): Boolean = false
}
```

Usage:

```kotlin
@AndroidEntryPoint
class SettingsActivity : BaseActivity<ActivitySettingsBinding>(ActivitySettingsBinding::inflate) {

    private val viewModel by viewModels<SettingsViewModel>()

    override fun statusBarInsetTarget(): View = mBinding.toolbar

    override fun initViews() {
        mBinding.listOptions.adapter = optionAdapter
    }

    override fun onClickViews() {
        mBinding.btnBack.setOnClickListener { finish() }
        mBinding.switchDarkMode.setOnCheckedChangeListener { _, checked ->
            viewModel.dispatch(SettingsAction.ToggleDarkMode(checked))
        }
    }

    override fun observeData() { … }
}
```

The constructor-reference form (`ActivitySettingsBinding::inflate`) is what makes the
generic work. Passing a layout id instead and inflating manually gives up the type safety
that is the whole reason ViewBinding exists.

## `BaseFragment<VB>`

```kotlin
abstract class BaseFragment<VB : ViewBinding>(
    private val inflate: (LayoutInflater, ViewGroup?, Boolean) -> VB
) : Fragment() {

    lateinit var mBinding: VB

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        mBinding = inflate(inflater, container, false)
        return mBinding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        initViews()
        onResizeViews()
        onClickViews()
        observerData()
    }

    open fun initViews() {}
    open fun onResizeViews() {}
    open fun onClickViews() {}
    open fun observerData() {}
}
```

### The binding-lifetime trap

A Fragment's view is destroyed and recreated while the Fragment instance lives on. A
`lateinit var mBinding` held across that boundary is a leak and a crash source. Two
mitigations, both acceptable:

1. Never touch `mBinding` outside the `onViewCreated` → `onDestroyView` window, which the
   four hooks and `viewLifecycleOwner`-scoped collection already give you.
2. Null it in `onDestroyView` if the base class supports it.

What is never acceptable: a callback registered on a long-lived object (a manager, an
EventBus, a repository) that writes into `mBinding`. Route it through the ViewModel.

## ViewBinding vs DataBinding

Prefer ViewBinding. It is generated for every layout with no opt-in per file, has no
runtime binding expressions to debug, and does not tempt logic into XML.

A project with `dataBinding = true` already enabled will have `<layout>`-wrapped files;
leave them alone and use the generated binding the same way. Do not convert a layout in
either direction as a side effect of another task, and do not add a binding expression
(`android:text="@{vm.title}"`) to a new layout — the rendering decision belongs in
`render(state)` where it can be read.

## `BaseViewModel<Action, SideEffect>`

```kotlin
abstract class BaseViewModel<A : IAction, E : ISideEffect> : ViewModel() {

    private val _sideEffect = Channel<E>(Channel.BUFFERED)
    val sideEffect: Flow<E> = _sideEffect.receiveAsFlow()

    abstract fun dispatch(action: A)

    protected fun postSideEffect(effect: E) {
        viewModelScope.launch { _sideEffect.send(effect) }
    }

    protected fun launchBlock(
        dispatcher: CoroutineDispatcher = Dispatchers.Default,
        block: suspend CoroutineScope.() -> Unit
    ): Job = viewModelScope.launch(dispatcher + exceptionHandler, block = block)
}
```

A concrete ViewModel:

```kotlin
@HiltViewModel
class DocumentViewModel @Inject constructor(
    private val getDocuments: GetDocumentsUseCase,
    private val deleteDocument: DeleteDocumentUseCase
) : BaseViewModel<DocumentAction, DocumentSideEffect>() {

    private val _uiState = MutableStateFlow(DocumentUiState())
    val uiState: StateFlow<DocumentUiState> = _uiState.asStateFlow()

    override fun dispatch(action: DocumentAction) {
        when (action) {
            is DocumentAction.Refresh -> load()
            is DocumentAction.ClickDocument -> postSideEffect(
                DocumentSideEffect.OpenViewer(action.document.uri)
            )
            is DocumentAction.Delete -> launchBlock {
                deleteDocument(action.document)
                postSideEffect(DocumentSideEffect.ShowToast(ToastMessage.Resource(R.string.deleted)))
            }
        }
    }
}
```

`when` over a sealed interface with no `else` is exhaustive — adding an action to the
contract then becomes a compile error until it is handled, which is the point.

### Channel vs SharedFlow for side effects

| | Behaviour |
| :--- | :--- |
| `Channel(BUFFERED).receiveAsFlow()` | each effect delivered exactly once, to one collector; buffered while the view is in the background |
| `MutableSharedFlow(replay = 0)` | dropped if nothing is collecting; use when a missed effect is genuinely fine |
| `StateFlow` | **wrong** — replays the last value to the next collector, so navigation fires again on rotation |

## Collecting on the view side

```kotlin
override fun observerData() {
    viewLifecycleOwner.lifecycleScope.launch {
        viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            launch { viewModel.uiState.collect(::render) }
            launch { viewModel.sideEffect.collect(::handleEffect) }
        }
    }
}

private fun handleEffect(effect: DocumentSideEffect) {
    when (effect) {
        is DocumentSideEffect.OpenViewer -> router.navigateTo(requireContext(), Viewer(effect.uri))
        is DocumentSideEffect.ShowToast -> toast(effect.message)
        DocumentSideEffect.ScrollToHead -> mBinding.listDocuments.scrollToPosition(0)
    }
}
```

In an Activity the same block uses `lifecycleScope` and `this` as the lifecycle owner.

If the project has `observe` / `observeLatestSuspend` extensions in `core/common/ext`,
use them — they wrap exactly this and the codebase reads consistently. Check before
hand-rolling.

## Insets and system bars

Edge-to-edge is the default on modern targets, so a screen that does nothing draws under
the status bar. Handle it in `onResizeViews()` / `statusBarInsetTarget()` using whatever
the project standardised on — `ViewCompat.setOnApplyWindowInsetsListener`, or an
`immersionbar`-style helper if one is already in the dependency list. Do not introduce a
second mechanism alongside an existing one.
