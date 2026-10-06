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

# Initialize for Claude Code instead of Antigravity
aha init --platform claude
```

### What `aha init` does
1. **Injects `.agents/`**: Deploys rules, skills, agent personas, deterministic hooks, and MCP configs into your project.
2. **Slices Delegation Rule into `AGENTS.md`**: Adds marker-delimited instructions at your project root, keeping existing notes intact.
3. **Local Git Exclusion**: Excludes installed files in `.git/info/exclude` so `git status` stays clean without altering your project's `.gitignore`.

### Claude Code (`--platform claude`)
The same track, installed for Claude Code:
- **`.claude/`**: skills, rules (`.claude/rules/*.md` load always), agents, and hooks. Paths and tool names are rewritten for Claude (`view_file` -> `Read`, `invoke_subagent` -> `Agent`, ...).
- **`CLAUDE.md`**: the delegation rule, spliced in as a marked block, like `AGENTS.md`.
- **`.claude/settings.json`**: hooks are merged in and run through `hooks/claude_adapter.py`, which converts Claude's hook payloads for the unchanged Antigravity scripts. Your own settings and hooks are kept.
- **`.mcp.json`**: harness MCP servers are added; servers you already have win.
- **Models**: subagents are pinned to `sonnet` (`--subagent-model` to change it). `orchestrator` and `oracle` stay on `opus`. Run `claude --agent orchestrator` to plan on Opus in the main session.
- **No git exclusion**: nothing is written to `.git/info/exclude`. Commit `.claude/`, `CLAUDE.md` and `.mcp.json` so your team shares the harness.

Both platforms can be installed side by side. `update`, `status` and `undo` act on whichever one is installed; if both are, pass `--platform`.

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
| `aha verifier [mode]` | Shows or sets this worktree's verifier mode (`minimal`, `compact`, `full`); `--reset` returns to the project default, `--device <serial>` sets the device this worktree prefers. |
| `aha mcp` | Lists the harness MCP servers and whether each is on. `aha mcp on figma` / `aha mcp off figma` switch optional servers; mobilerun is not switched here (see below). |
| `aha worktree add <path> [git args]` | Runs `git worktree add`, then installs the same harness (platform, track, profile, verifier default) into the new worktree. |

Flags: `--platform {antigravity,claude}`, `--subagent-model <model>`, `--track {xml,compose}`, `--profile <name>`, `--skills <names>`, `--agents <names>`, `--rules <names>`, `--no-hooks`, `--no-mcp`, `--dry-run`.

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
- **`verifier`**: Aggregates build verification and drives on-device testing via the `mobilerun` MCP server.
- **`figma-analyzer` / `figma-asset-extractor` / `figma-xml-developer`** (or `figma-compose-developer`): 4-stage pipeline converting Figma specs into production code.

### 2. Deterministic Safety Hooks
- **`rule_gate.py` (`PreToolUse`)**:
  - Rejects inline/block comments in Kotlin code (KDoc allowed).
  - Enforces `strings.xml`: **never hardcode user-facing strings on Android**.
  - Enforces `@color/*` tokens (no raw hex).
  - On XML track, rejects redundant `<shape>`/`<selector>` XML drawables in favor of ShapeView `app:shape_*` attributes.
- **`write_guard.py` (`PreToolUse`)**: Blocks source file edits from the root session to enforce delegation.
- **`device_gate.py` (`PreToolUse`)**: Pins every `adb` command and every `mobilerun` call to the device this worktree leased (see [Parallel Worktrees](#6-parallel-worktrees--devices)), and blocks Gradle `install*`/`connected*` tasks.
- **`stop_verifier.py` (`Stop`)**: Holds goal loops open until verification passes.

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
4. **`verifier`**: Builds APK and validates on-device visual conformance via `mobilerun`.

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

- `verifier` in `full` mode assembles through `gradle-run`, installs with `device_lease.py install --launch`, then drives the screen with `mobilerun`.
- The host needs only `adb`, Python (for hooks and scripts) and Node (for `npx`).

### 6. Parallel Worktrees & Devices
Run one agent session per git worktree; the harness keeps them off each other's builds and devices.

```bash
aha worktree add ../app-login -b feature/login   # new worktree, same harness
cd ../app-login && aha verifier full              # this worktree verifies on device
```

- **Gradle**: each worktree builds in its own directory; `gradle-run` serializes builds within one worktree.
- **Devices**: `.agents/scripts/device_lease.py` keeps machine-wide leases in `~/.aha/devices/leases.json` (`AHA_HOME` relocates it). A worktree holds at most one device and a device belongs to at most one worktree. The `device-gate` hook takes the lease on the first device call and rewrites `adb` to `adb -s <serial>` and mobilerun's `device` argument to the leased serial, so no serial is ever configured. When every device is busy the call is denied with the holder's name, and the agent queues with `device_lease.py acquire --wait 600`. Leases expire after 30 minutes of inactivity, or as soon as their worktree directory is deleted.
- **MCP servers**: mobilerun is on in a worktree exactly when its verifier mode is `full`, and off otherwise; `aha verifier full` / `aha verifier compact` switch it. figma is on when the figma agents are installed; choose explicitly with `--mcp figma` / `--mcp none` at install, or `aha mcp on|off figma` later. On Antigravity the switch edits the worktree's untracked `.agents/mcp_config.json`. On Claude Code, `.mcp.json` (committed) always defines mobilerun, and each worktree enables or rejects it in its git-ignored `.claude/settings.local.json` (`enabledMcpjsonServers` / `disabledMcpjsonServers`). Restart the agent session after switching.
- **Settings per worktree**: `aha verifier <mode>` and `--device <serial>` write untracked files under `.agents/state/` (git-ignored), so a committed Claude install stays clean while each worktree runs its own mode.
- **Inspect**: `python .agents/scripts/device_lease.py list` shows which worktree holds which device; `release` frees this worktree's device.

With one phone, verifiers in different worktrees take turns. Attach another device or start an emulator to verify in parallel.

---

## Contributing & Development

Harness payload assets live under `assets/xml/` and `assets/compose/`. Shared files (hooks, `loop.py`, neutral skills) must remain byte-identical across both tracks.

Run test suite:
```bash
python -m unittest discover -s tests
```
