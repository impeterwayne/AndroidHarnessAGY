# Deriving MVI Contract from Figma Design

Guidance on translating Figma screen designs and prototype reactions into a structured MVI Contract (`UiState`, `Intent`/`Event`, `SideEffect`).

---

## 1. Deriving `UiState` from Figma Frames & Variants

Observe screens and component variants in Figma:

| Figma Visual Element | Inferred `UiState` Field | Code Example |
|---|---|---|
| Dynamic text (user name, balance, connected device) | Dynamic data field | `val deviceName: String = ""` |
| Component variants: `Default`, `Loading`, `Error`, `Empty` | Screen state flags or sealed class | `val isLoading: Boolean = false`, `val errorMessage: String? = null` |
| Repeating cards / lists | Immutable list | `val items: ImmutableList<CastItemUiModel> = persistentListOf()` |
| Toggle / Switch / Checkbox | Boolean flag | `val isAutoConnectEnabled: Boolean = false` |
| Tab / Segmented button selection | Enum / selected index | `val selectedTab: TabType = TabType.PHOTO` |

---

## 2. Deriving `Intent` / `Event` from Clickable Nodes & Reactions

Inspect clickable nodes and prototype reactions (`get_reactions`):

| Figma Reaction / Interactive Node | Corresponding MVI Intent / Event |
|---|---|
| Click Back / Close button | `data object OnBackClicked : ScreenEvent` |
| Click Primary CTA (e.g. "Connect", "Start Casting") | `data object OnConnectClicked : ScreenEvent` |
| Click list item | `data class OnItemClicked(val itemId: String) : ScreenEvent` |
| Toggle switch | `data class OnToggleChanged(val isChecked: Boolean) : ScreenEvent` |
| Pull to refresh | `data object OnRefresh : ScreenEvent` |
| Type into search / input field | `data class OnSearchQueryChanged(val query: String) : ScreenEvent` |

---

## 3. Deriving `SideEffect` from Navigation & One-Off Feedback

From reactions that trigger screen transitions, bottom sheets, or snackbars:

```kotlin
sealed interface ScreenSideEffect {
    data class NavigateToDetail(val deviceId: String) : ScreenSideEffect
    data object NavigateBack : ScreenSideEffect
    data class ShowToast(val message: String) : ScreenSideEffect
    data object OpenConnectSheet : ScreenSideEffect
}
```
