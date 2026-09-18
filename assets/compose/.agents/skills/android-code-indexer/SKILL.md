---
name: android-code-indexer
description: >
  Android code indexing agent for multi-module MVVM / Clean Architecture projects.
  Maintains a structured, ultra-compact code graph in `docs/code-index/` optimized for
  fast reasoning and minimal token usage.

  ALWAYS trigger this skill when the user:
  - Asks to analyze, navigate, or understand an Android project
  - Mentions modules like :app, :feature:*, :core:*
  - Asks about ViewModels, UseCases, Repositories, DataSources
  - Wants to trace a call chain (UI → ViewModel → UseCase → Repository → DataSource)
  - Asks about Compose vs XML screens or migration between them
  - Mentions "code index", "index the project", or "update the index"
  - Asks where a class or screen lives in the project
  - Wants to detect architecture violations or circular dependencies
  - Shares .kt files belonging to an Android project
---

# Android Code Indexer

## 0. ALWAYS START HERE

Before doing anything, run this check:

```
IF docs/code-index/ exists  → READ all .md files inside it first
                        → then update INCREMENTALLY (only changed nodes)
IF docs/code-index/ missing → Scan all provided files
                        → CREATE full index from scratch
```

Never analyze code without reading `docs/code-index/` first. Fall back to raw files only when data is missing.

---

## 1. Index Structure

```
docs/code-index/
├── _meta.md                  # module map, legend, last-updated
├── modules/
│   ├── app.md                # one file per Gradle module
│   ├── feature_login.md
│   ├── feature_home.md
│   └── core_network.md
├── graph/
│   ├── navigation.md         # screen-to-screen flow  (A => B)
│   ├── calls.md              # function/class calls    (A -> B)
│   └── data_flow.md          # data propagation        (A ~> B)
└── issues.md                 # architecture violations
```

**Size rule:** Each file MUST stay under 250 lines. If a file approaches the limit, split by feature or layer and add a pointer in `_meta.md`.

---

## 2. Graph Format (STRICT — never deviate)

| Relationship | Symbol | Example |
|---|---|---|
| Call (function/class) | `->` | `LoginViewModel -> LoginUseCase` |
| Navigation | `=>` | `LoginScreen => HomeScreen` |
| Data flow | `~>` | `LoginRepository ~> LoginViewModel` |
| XML→Compose migration | `~>` | `LoginScreen(XML) ~> LoginScreen(Compose)` |

---

## 3. Android Architecture Mapping

Always classify every symbol into one layer:

```
UI  →  ViewModel  →  Repository  →  DataSource
```

### UI Layer rules (CRITICAL)
- Compose screen → `ScreenName(Compose)`
- XML screen     → `ScreenName(XML)`
- If BOTH exist  → create a migration link: `ScreenName(XML) ~> ScreenName(Compose)`
- Fragment/Activity hosting XML → tag as `(XML)`

### What TO store
- Screen names + their type (XML / Compose)
- ViewModel names
- Repository interfaces + implementations
- DataSource names (local/remote)
- Navigation routes / NavGraph entries
- Call relationships between the above

### What NOT to store
- XML layout content
- Compose UI composable code
- Implementation details (function bodies)
- Gradle config details
- Resource files

---

## 4. Module File Format

Each `modules/<name>.md` must follow this template exactly:

```markdown
# Module: :feature:login

## exports
- LoginViewModel
- LoginScreen(Compose)

## dependencies
- :core:network
- :core:ui

## used_by
- :app

## symbols

### UI
- LoginScreen(Compose)
- LoginScreen(XML)          ← only if exists

### ViewModel
- LoginViewModel

### Repository
- LoginRepository (interface)
- LoginRepositoryImpl

### DataSource
- LoginRemoteDataSource
- LoginLocalDataSource

## graph (local)
LoginScreen(Compose) -> LoginViewModel
LoginScreen(XML) ~> LoginScreen(Compose)
LoginViewModel -> LoginRepository
LoginRepository ~> LoginViewModel
LoginRepositoryImpl -> LoginRemoteDataSource
```

---

## 5. `_meta.md` Format

```markdown
# Code Index Meta
last_updated: YYYY-MM-DD
total_modules: N

## Legend
->  CALL
=>  NAVIGATION
~>  DATA FLOW / MIGRATION

## Module Map
| Module              | File                          | Status  |
|---------------------|-------------------------------|---------|
| :app                | modules/app.md                | indexed |
| :feature:login      | modules/feature_login.md      | indexed |
| :core:network       | modules/core_network.md       | indexed |

## Split Files (if any)
| Original            | Split into                              |
|---------------------|-----------------------------------------|
| feature_home.md     | feature_home_ui.md, feature_home_data.md|
```

---

## 6. Global Graph Files

### `graph/navigation.md`
Only screen-to-screen flows across the whole project:
```
# Navigation Graph
LoginScreen(Compose) => HomeScreen(Compose)
HomeScreen(Compose)  => ProfileScreen(Compose)
HomeScreen(Compose)  => DetailScreen(XML)
```

### `graph/calls.md`
Cross-module call relationships:
```
# Call Graph
LoginViewModel     -> LoginUseCase
LoginUseCase       -> LoginRepository
LoginRepositoryImpl -> NetworkDataSource   # :core:network
```

### `graph/data_flow.md`
Data propagation (StateFlow, LiveData, callbacks):
```
# Data Flow
LoginRepositoryImpl ~> LoginViewModel
UserPrefsDataSource ~> SettingsViewModel
```

---

## 7. `issues.md` Format

```markdown
# Architecture Issues
last_checked: YYYY-MM-DD

## CRITICAL
- [C1] LoginScreen(Compose) -> LoginRepository  ← UI bypasses ViewModel+UseCase

## WARNING
- [W1] HomeViewModel -> NetworkDataSource  ← ViewModel skips Repository layer

## INFO
- [I1] ProfileScreen(XML) exists alongside ProfileScreen(Compose) — migration in progress
```

Issue severity:
- **CRITICAL** — layer skip of 2+ levels (e.g. UI → Repository)
- **WARNING** — layer skip of 1 level (e.g. ViewModel → DataSource)
- **INFO** — parallel XML+Compose, missing UseCase, etc.

---

## 8. Update Rules

| Event | Action |
|---|---|
| ADD new file | Index new symbols + add relations to graph files |
| MODIFY file | Update only affected nodes in relevant module file + graph files |
| DELETE file | Remove all references from module file, graph files, and issues.md |
| Rename | Treat as DELETE + ADD |

After every update, refresh `_meta.md` with the new `last_updated` date.

---

## 9. Output Format

After every indexing run, always output:

```
## Index Update Summary

### Files Updated
- docs/code-index/modules/feature_login.md  (ADDED: LoginUseCase)
- docs/code-index/graph/calls.md            (ADDED: LoginUseCase -> LoginRepository)
- docs/code-index/_meta.md                  (last_updated refreshed)

### Changed Graph
+ LoginViewModel -> LoginUseCase
+ LoginUseCase -> LoginRepository
+ LoginRepositoryImpl -> LoginRemoteDataSource

### Architecture Issues
⚠️  [W1] LoginViewModel -> NetworkDataSource — skips Repository layer
```

---

## 10. Compose Migration Detection

When scanning, check every screen name for dual existence:

```
IF ScreenName(XML) AND ScreenName(Compose) both exist:
  → Add to modules/<feature>.md under both UI entries
  → Add migration link to graph/data_flow.md:
    ScreenName(XML) ~> ScreenName(Compose)
  → Add INFO issue to issues.md
```

---

## Reference Files

- `references/templates.md` — copy-paste templates for each index file type
- `references/violation_rules.md` — full list of architecture violation detection rules
