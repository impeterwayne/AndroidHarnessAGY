# GenesysCompose — Project Architecture

## Overview

Android app built with **Jetpack Compose**, following **Clean Architecture + MVI (Orbit MVI)**, DI with **Hilt**.

**Root package**: `com.genesys.codebase` | **Min SDK**: 24 | **Compile SDK**: 36

---

## Module Dependency

```
:app
 ├── :feature:*          (each feature is a separate module, e.g. :feature:home)
 ├── :core:designsystem
 ├── :core:data
 ├── :core:domain
 ├── :core:database
 ├── :core:network
 ├── :core:model
 ├── :core:navigation
 ├── :core:datastore
 └── :core:common
```

### Core module layer (top-down dependency flow):

```
:core:data  ──────────────────────────────────┐
  ├── depends on :core:domain                 │
  ├── depends on :core:network                │
  ├── depends on :core:database               │
  ├── depends on :core:model                  │
  └── depends on :core:common                 │
                                              │
:core:domain                                  │
  ├── depends on :core:model                  │
  └── depends on :core:common                 │
                                              │
:core:network   → depends on :core:model      │
:core:database  → depends on :core:model      │
:core:common    → standalone (no core deps)   │
:core:model     → standalone (no core deps)   │
:core:navigation→ depends on :core:model      │
:core:designsystem → standalone (no core deps)│
```

### Feature module pattern:

```
:feature:*
  ├── depends on :core:domain       (UseCase)
  ├── depends on :core:model        (data classes)
  ├── depends on :core:navigation   (type-safe routes)
  └── depends on :core:designsystem (UI components)
```

> Feature modules do **not** depend directly on `:core:data`, `:core:network`, or `:core:database`. They only communicate through `:core:domain` (UseCases + Repository interfaces).

---

## Cross-Module Data Flow

```
Feature Screen → ViewModel → UseCase → Repository Interface → Repository Impl
                (:feature:*)  (:core:domain)  (:core:domain)     (:core:data)
                                                                      │
                                                          ┌───────────┼───────────┐
                                                          ▼           ▼           ▼
                                                     ApiService   Room DAO    MMKVData
                                                   (:core:network) (:core:database) (:core:data)
```

**Explanation**:
1. **ViewModel** (in feature) calls **UseCase** (in `:core:domain`)
2. **UseCase** calls **Repository interface** (defined in `:core:domain`)
3. **Repository implementation** (in `:core:data`) is injected by Hilt, aggregating 3 sources: API (network), Room DB (database), MMKV (local cache)
4. Result is returned via `Flow<Result<T>>` with the sealed class `Result`: `Loading`, `Success`, `Error`, `Initial`

---

## MVI Pattern (Orbit MVI)

Each feature screen applies the pattern:

```
[Contract.kt]     → Defines: UiState (data class), Action/Event (sealed interface), SideEffect
[ViewModel.kt]    → @HiltViewModel, ContainerHost<UiState, SideEffect>, processes Action with intent{} + reduce{}
[Screen.kt]       → @Composable, takes UiState + callback lambda, purely stateless
[Route.kt/Graph]  → @Composable, bridge between Navigation and Screen: hiltViewModel(), collectAsStateWithLifecycle(), collectSideEffect()
```

---

## Role of Each Core Module

| Module | Role | Contents |
|---|---|---|
| **:core:model** | Shared data classes | Parcelable models, Moshi `@Json` / Gson annotations |
| **:core:common** | Shared utilities | `Result` sealed class, `BaseViewModel`, `TimeUtils`, extension functions |
| **:core:navigation** | Type-safe navigation | Route declarations (`@Serializable`, `@Parcelize`), Navigation 3 contracts |
| **:core:network** | HTTP layer | Retrofit `ApiService`, `NetworkModule` (Hilt), OkHttp config, response DTOs |
| **:core:database** | Persistence layer | Room `@Database`, `@Dao`, `@Entity`, TypeConverters, EntityMappers, `DatabaseModule` (Hilt) |
| **:core:domain** | Business logic contracts | Repository interfaces, UseCases (`@Inject constructor`) |
| **:core:data** | Glue layer / implementations | Repository implementations, `DataModule` (Hilt `@Binds`), `MMKVData` (key-value store) |
| **:core:designsystem** | UI Design System | `AppTheme` (CompositionLocal: colors, typography, spacing, shapes, strokes), reusable components (`AppText`, `AppPrimaryButton`, `AppSecondaryButton`, `AppChip`, `AppPanel`, `AppDivider`, `AppBottomBar`, `AddActionButton`, `ErrorState`) |

---

## Build Convention Plugins

`build-logic/convention/` provides convention plugins used across modules:

| Plugin ID | Used for |
|---|---|
| `codebase.android.library` | Core library modules |
| `codebase.android.feature` | Feature modules (includes Compose + Hilt + Navigation) |
| `codebase.android.hilt` | Hilt + KSP |
| `codebase.android.compose` | Compose compiler |
| `codebase.jvm.library` | Pure Kotlin modules |

---

## Tech Stack Summary

Compose (BOM 2026.05.00) · Navigation 3 · Orbit MVI 11 · Hilt 2.60.1 · Landscapist Glide 2.4.4 · KSP · Retrofit 2.9 · Room 2.8 · MMKV 1.3 · OkHttp · Timber · ImmersionBar
