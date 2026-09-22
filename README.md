# AndroidHarnessAGY (`aha`)

> **Production-ready agentic engineering harness for Android development with Google Antigravity IDE & CLI (`agy`).**

AndroidHarnessAGY equips Antigravity with senior Android engineering guardrails, architectural rules, deterministic safety hooks, and specialized subagents. Everything is injected cleanly into `.agents/` with zero git pollution.

It provides two independent UI tracks (never merged):
- **`xml`** (**default**): Views & XML layouts, ViewBinding, [ShapeView](https://github.com/impeterwayne/ShapeView), Glide (`GlideImageView`), Epoxy controllers, and `rules/xml.md`.
- **`compose`**: Jetpack Compose, `AppTheme` tokens, Landscapist Glide, Orbit MVI, and `rules/android.md`.

---

## Global Setup (Clone & Install)

Because the harness is not yet published to the npm registry, clone the repository and install it globally from local source:

```bash
git clone https://github.com/impeterwayne/AndroidHarnessAGY.git
cd AndroidHarnessAGY

# Install globally via npm (recommended):
npm install -g .
# Or link during local development:
npm link
```

Verify the CLI is accessible:
```bash
aha --help
```

---

## Quickstart

Navigate to your Android project and initialize the harness:

```bash
# Initialize View/XML harness (default)
aha init

# Initialize Jetpack Compose harness
aha init --track compose

# Initialize with a specific profile
aha init --profile figma
```

### What `aha init` does
1. **Injects `.agents/`**: Deploys rules, skills, agent personas, deterministic hooks, and MCP configs into your project.
2. **Slices Delegation Rule into `AGENTS.md`**: Adds marker-delimited instructions at your project root, keeping existing notes intact.
3. **Local Git Exclusion**: Excludes installed files in `.git/info/exclude` so `git status` stays clean without altering your project's `.gitignore`.

---

## CLI Reference

| Command | Description |
| :--- | :--- |
| `aha init [target]` | Injects harness into `target` (default: `.`, default track: `xml`). |
| `aha update [target]` | Syncs latest harness files while preserving your local edits. |
| `aha update [target] --prune` | Updates and removes files omitted from the active profile. |
| `aha status [target]` | Displays installed version, upstream commits, and drifted files. |
| `aha undo [target]` | Reverses installation cleanly, restoring `AGENTS.md` and excludes. |
| `aha list` | Lists all available rules, agents, skills, and hooks. |

Flags: `--track {xml,compose}`, `--profile <name>`, `--skills <names>`, `--agents <names>`, `--rules <names>`, `--no-hooks`, `--no-mcp`, `--dry-run`.

---

## Profiles & Tracks

Select tailored payloads within a track using `--profile <name>`:

| Profile | Use Case | `xml` (Default) | `compose` |
| :--- | :--- | :---: | :---: |
| **`full`** *(default)* | Entire track payload | 31 skills, 8 agents, 3 rules | 42 skills, 8 agents, 3 rules |
| **`android`** | Core Android dev without Figma pipeline | 28 / 5 / 2 | 39 / 5 / 2 |
| **`figma`** | Design-to-code sprint (spec, assets, UI) | 13 / 6 / 3 | 15 / 6 / 3 |
| **`minimal`** | Lean review, code health, goal loops | 12 / 5 / 1 | 12 / 5 / 1 |

Inspect track contents anytime with `aha list` or `aha list --track compose`.

---

## Architecture & Guardrails

### 1. Delegation Model (`AGENTS.md`)
The root conversation session plans and delegates; it never directly edits source files.
- **`explore`**: Fast repository search, discovery, and file indexing.
- **`oracle`**: Architecture review, edge cases, and compliance.
- **`executor`**: Dispatched for code changes (compiles and tests what it writes).
- **`verifier`**: Aggregates build verification and drives on-device testing via `scrcpy`.
- **`figma-analyzer` / `figma-asset-extractor` / `figma-xml-developer`** (or `figma-compose-developer`): 4-stage pipeline converting Figma specs into production code.

### 2. Deterministic Safety Hooks
- **`rule_gate.py` (`PreToolUse`)**:
  - Rejects inline/block comments in Kotlin code (KDoc allowed).
  - Enforces `strings.xml`: **never hardcode user-facing strings on Android**.
  - Enforces `@color/*` tokens (no raw hex).
  - On XML track, rejects redundant `<shape>`/`<selector>` XML drawables in favor of ShapeView `app:shape_*` attributes.
- **`write_guard.py` (`PreToolUse`)**: Blocks source file edits from the root session to enforce delegation.
- **`device_gate.py` & `stop_verifier.py`**: Ensures exclusive device leases (`andrun`) and holds goal loops open until verification passes.

---

## Developer Workflows

Once injected into an Android project, AHA orchestrates everyday engineering through Antigravity:

### 1. Feature Implementation & Bug Fixing
Prompt Antigravity naturally:
> *"Implement the Profile screen with ViewBinding and ShapeView"*  
> *"Fix the race condition in AuthRepository"*

- **Automated Delegation**: The root session plans and dispatches `executor` for code changes and `explore` for codebase discovery.
- **Safety Gates**: `rule_gate.py` rejects code comments in Kotlin, enforces `strings.xml` (no hardcoded user-facing strings), and blocks raw hex colors.
- **Verification**: `verifier` runs `./gradlew test` and validates the build before completing.

### 2. Figma-to-Code Pipeline
Paste any Figma URL or frame ID:
> *"Implement https://www.figma.com/design/AbCdEf12345/AppUI?node-id=102-456"*

Triggers the 4-stage automated pipeline:
1. **`figma-analyzer`**: Extracts layout hierarchy, variants, and component specs (`docs/<feature>/figma-spec.md`).
2. **`figma-asset-extractor`**: Exports SVGs to `ic_*.xml` vector drawables and snaps color/dimen tokens.
3. **`figma-xml-developer`** (or `figma-compose-developer`): Generates layouts, ShapeView attributes, and ViewModel contracts.
4. **`verifier`**: Builds APK and validates on-device visual conformance via `scrcpy`.

### 3. High-Rigour Mode (`ultrawork`)
For complex refactors, multi-module features, or high-stakes bug fixes:
> *"ultrawork: Refactor network layer to support offline caching"*

- Classifies intent and sets up formal planning.
- Registers an append-only, durable goal ledger via `loop.py` that survives LLM context compaction.
- `stop_verifier.py` prevents the agent from finishing until all goals pass with concrete verification evidence.

### 4. Code Review & Lean Audits
Review changes before merging or clean up technical debt:
> *"Review my current git diff"* (or `/code-review`)  
> *"Audit this module for over-engineering"* (or `/lean-audit`)  
> *"Simplify this diff using stdlib/KTX idioms"* (or `/lean-review`)

- Multi-agent review fans out discovery to `explore` and architectural critique to `oracle`.
- Enforces lean engineering: YAGNI, Kotlin stdlib/KTX reuse, and zero unnecessary boilerplate.

### 5. On-Device Testing & Emulation
Verify UI and runtime behavior on real devices:
> *"Run the app on my connected device and verify the login flow"*

- Managed by `device_gate.py` and `scrcpy_daemon.py` to coordinate exclusive device leases (`andrun`) across sessions.

---

## Contributing & Development

Harness payload assets live under `assets/xml/` and `assets/compose/`. Shared files (hooks, `loop.py`, neutral skills) must remain byte-identical across both tracks.

Run test suite:
```bash
python -m unittest discover -s tests
```
