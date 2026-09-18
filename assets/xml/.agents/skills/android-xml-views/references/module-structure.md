# Module structure for an XML-view app

Two shapes are both legitimate here. Read `settings.gradle(.kts)` before assuming which
one you are in, and do not propose a migration nobody asked for.

## Shape A — multi-module with convention plugins

```
settings.gradle.kts        includeBuild("build-logic") + every module
build-logic/convention/    AndroidLibraryConventionPlugin, AndroidFeatureConventionPlugin,
                           AndroidHiltConventionPlugin, KotlinJvm
gradle/libs.versions.toml  the single source of dependency versions
app/                       Application, DI wiring, the router implementation, launcher
core/model/                pure data classes, enums — no Android imports
core/domain/               use cases and repository interfaces
core/data/                 repository implementations
core/database/             Room
core/datastore/            DataStore / prefs
core/network/              Retrofit, OkHttp, DTOs
core/common/               BaseViewModel, IAction, ISideEffect, extensions, utils
core/ui/                   base classes (including BaseEpoxyViewBindingHolder), shared
                           layouts, design-system resources, custom views, shared bottom
                           sheets, navigation contracts
core/ads/                  ad wrappers, if the app has them
feature/<name>/            one screen or one coherent group of screens
baselineprofile/           startup profile generation
sdk/ or libs/              vendored third-party source
```

### Dependency direction

`app` → `feature/*` → `core/ui` → `core/domain` → `core/model`.

Features never depend on each other. When feature A must open a screen in feature B, both
depend on a `ScreenDestination` type in `core/ui` and `app` supplies the `AppRouter`
implementation that knows the Activities. That indirection is the reason the graph stays
acyclic.

`core/model` has no Android imports at all. If a model needs `Uri`, it holds a `String` and
the UI layer parses it.

### A new feature module

`settings.gradle.kts`:

```kotlin
include(":feature:newthing")
```

`feature/newthing/build.gradle.kts`:

```kotlin
plugins {
    id("itg.android.feature")
    alias(libs.plugins.ksp)
}

android {
    namespace = "com.<app>.feature.newthing"

    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    implementation(project(":core:ui"))
    implementation(libs.epoxy)
    ksp(libs.epoxyProcessor)
    implementation(libs.glide)
    implementation(libs.glide.image.view)
    implementation(libs.shape.view)
}
```

The convention plugin already applied the library and Hilt plugins, the compile/target
SDK, Java and Kotlin settings, and the `core:ui` / `core:model` / `core:domain` /
`core:common` dependencies. **Do not restate any of that in the module script** — the
whole point of `build-logic` is that it is stated once. A module script that sets
`compileSdk` itself has already drifted.

`viewBinding = true` is per-module and does have to be repeated, because it is a
`buildFeatures` flag the convention plugin deliberately leaves to the module. So is
`ksp(libs.epoxyProcessor)` — a feature module with Epoxy models and no processor compiles
its Kotlin and then fails on every missing `…Model_`.

Check the exact plugin ids in `build-logic/convention/build.gradle.kts` — the `itg.`
prefix above is this codebase's; another project will differ.

### Versions

Every dependency comes from `gradle/libs.versions.toml` as `libs.<alias>`. A raw
coordinate string in a module script is a drift bug waiting to happen; if the library is
not in the catalog, add it there first.

## Shape B — single module

A single-module app with Groovy build scripts and a `versions.gradle` `ext` block is the
other common shape on this track. The package layout does the work the module graph did:

```
app/src/main/java/com/<app>/
  ui/bases/           BaseActivity, BaseFragment, BaseDialog, BaseBottomSheetDialogFragment,
                      BaseEpoxyViewBindingHolder, BaseViewModel
  ui/bases/ext/       ActivityExt, ContextExt, ViewExt, ImageViewExt, ClickExt, StringExt
  ui/component/<screen>/   the screen's Activity/Fragment, ViewModel, Contract
  ui/component/<screen>/epoxy/  its controller and item models
  ui/component/custom/     project-specific custom views (if any)
  ui/component/dialog/     dialogs and sheets
  data/               repositories, DAOs, DTOs
  di/                 Hilt modules
  models/             data classes
  utils/              helpers
  res/layout/         one layout per screen, item_*.xml per row, dialog_*.xml per dialog
```

The architectural rules are identical — the boundaries are conventions rather than
compiler-enforced. That makes them easier to break, so be stricter, not looser: a
ViewModel importing from `ui/component` is the same violation it would be across a module
boundary.

## Layout file naming

| Prefix | For |
| :--- | :--- |
| `activity_<name>.xml` | an Activity's content view |
| `fragment_<name>.xml` | a Fragment's view |
| `item_<name>.xml` | a RecyclerView row |
| `dialog_<name>.xml` | a dialog |
| `layout_bottomsheet_<name>.xml` / `bottom_sheet_<name>.xml` | a bottom sheet — match what the project already uses |
| `view_<name>.xml` | a compound custom view's contents |

The binding class name is derived from the file name, so this naming is also what makes
`ItemDocumentBinding` findable.

## Where a file goes — the quick test

| The file | Goes in |
| :--- | :--- |
| a data class with no Android imports | `core/model` |
| a use case | `core/domain` |
| a Room entity or DAO | `core/database` |
| a repository implementation | `core/data` |
| a screen, its ViewModel, its contract, its Epoxy controller and item models | `feature/<name>` |
| a view used by two features | `core/ui` |
| a colour, dimen, style or shared drawable | `core/ui/res/values` |
| a string used by one screen | that feature's `res/values/strings.xml` |
| a string used by two screens | `core/ui/res/values/strings.xml` |
| the `AppRouter` implementation | `app` |

When two features need the same thing, it moves to `core/ui` once — it is not copied. When
one feature needs it, it stays local; hoisting on speculation is the other failure mode.
