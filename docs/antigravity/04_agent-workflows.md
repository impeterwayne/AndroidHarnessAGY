# Agent Workflows & Multi-Stage Pipelines

> **Topic:** Workspace Workflows, Multi-Stage Agent Pipelines, Coordinator-Worker Execution  
> **Target Runtime:** Google Antigravity 2.0, Antigravity CLI & Antigravity IDE  
> **Workspace Location:** `.agents/workflows/`

---

## 1. Executive Summary & Overview

Modern AI-assisted software engineering has evolved beyond single-turn prompt-and-response interactions. Complex engineering tasks—such as implementing a multi-module Clean Architecture flow, converting Figma designs into Jetpack Compose screens, or executing deep refactorings—require **multi-step, deterministic, and repeatable pipelines**.

In the **Google Antigravity** runtime, the `.agents/workflows/` directory acts as the workspace's repository of **executable workflow blueprints**.

```text
                           ┌───────────────────────────────┐
                           │   User / Slash Command        │
                           │   (e.g., /figma-to-compose)   │
                           └───────────────┬───────────────┘
                                           │
                                           ▼
                           ┌───────────────────────────────┐
                           │   .agents/workflows/<flow>.md │
                           │   (Pipeline Blueprint)        │
                           └───────────────┬───────────────┘
                                           │
                 ┌─────────────────────────┼─────────────────────────┐
                 ▼                         ▼                         ▼
    ┌─────────────────────────┐ ┌────────────────────┐ ┌─────────────────────────┐
    │ Phase 1: Context Scan   │ │ Phase 2: Execution │ │ Phase 3: Quality Gate   │
    │ (Progressive Skills)    │ │ (Spawn Subagents)  │ │ (Lint / Tests / Diff)   │
    └─────────────────────────┘ └────────────────────┘ └─────────────────────────┘
```

A workflow formalizes:
1. **Trigger conditions**: Slash commands (e.g., `/feature-mvi`, `/figma-to-compose`, `/code-review`), keywords, or coordinator decisions.
2. **Phase sequencing**: Strict progression through discovery, planning, subagent execution, quality gating, and artifact delivery.
3. **Subagent & tool assignments**: Explicitly binding specialized custom agents (`.agents/agents/`) and skills (`.agents/skills/`) to specific steps.
4. **Safety & quality checkpoints**: Human-in-the-loop review gates (`ask_question`, plan approvals) and verification steps before modifications are finalized.

---

## 2. The 5 Pillars of the Antigravity Workspace Contract

Antigravity organizes the agentic workspace into five specialized directories, each serving a distinct architectural role:

| Component | Directory / File | Scope | Primary Purpose |
| :--- | :--- | :--- | :--- |
| **Rules** | `.agents/rules/*.md`, `AGENTS.md` | Invariant Constraints | Guardrails and conventions that agents must **always** follow (e.g. Clean Architecture rules, no hardcoded strings). |
| **Skills** | `.agents/skills/<name>/SKILL.md` | Progressive Capabilities | On-demand domain knowledge and procedural instructions (e.g. how to use Figma MCP, how to write Compose animations). |
| **Agents** | `.agents/agents/<name>/agent.md` | Role & Persona Defs | Isolated worker definitions with tailored system prompts, tool whitelists, and model tiers (e.g. `figma-analyzer`, `figma-compose-developer`). |
| **Workflows** | `.agents/workflows/*.md` | Process Orchestration | End-to-end multi-phase pipelines that coordinate skills, subagents, and tools to achieve a complex milestone. |
| **Hooks** | `hooks.json` | Deterministic Intercepts | System-level lifecycle interceptors (e.g. PreToolUse gates blocking dangerous shell commands). |

```text
 ┌───────────────────────────────────────────────────────────────────────────┐
 │                                WORKFLOW                                   │
 │  Coordinates the entire lifecycle from prompt to verified deliverable     │
 │                                                                           │
 │   ┌───────────────┐      ┌─────────────────┐      ┌──────────────────┐   │
 │   │  Rules        │      │  Skills         │      │  Agents          │   │
 │   │  (Guardrails) │ ───► │  (Domain Tools) │ ───► │  (Specialists)   │   │
 │   └───────────────┘      └─────────────────┘      └──────────────────┘   │
 └─────────────────────────────────────┬─────────────────────────────────────┘
                                       ▼
                         ┌───────────────────────────┐
                         │ Verified Code & Artifacts │
                         └───────────────────────────┘
```

---

## 3. Anatomy of a Workflow File

Workflow definitions are written in Markdown (`.md`) with a structured YAML frontmatter header. They are stored in:
- **Workspace-level**: `.agents/workflows/<workflow-name>.md` (or `.agents/workflows/<name>/workflow.md`)
- **User-global level**: `~/.gemini/config/workflows/<workflow-name>.md`

### Standard YAML Frontmatter Schema

```yaml
---
name: figma-to-compose
description: End-to-end pipeline to inspect Figma screens, extract VectorDrawables, update theme tokens, and build stateless Compose UI with Orbit MVI.
trigger:
  slash_command: /figma-to-compose
  keywords:
    - "figma.com/design"
    - "figma.com/file"
    - "implement screen from figma"
inputs:
  - name: figma_url
    description: Full URL or node-id of the Figma design frame
    required: true
  - name: target_module
    description: Destination feature module (e.g. :feature:home)
    required: false
agents:
  - figma-analyzer
  - figma-asset-extractor
  - figma-compose-developer
skills:
  - figma-design-analyzer
  - figma-asset-extractor
  - figma-to-compose
  - android-resource-policy
  - orbit-mvi-feature-builder
checkpoints:
  require_plan_approval: true
  require_lint_pass: true
---
```

### Anatomy of Workflow Phases

Inside the Markdown body, workflows define a series of deterministic phases:

```markdown
# Figma to Jetpack Compose Workflow Pipeline

## Phase 1: Ingestion & Pre-flight Inspection
1. Extract file key and node-id from the provided Figma URL.
2. Delegate to figma-analyzer subagent to run get_design_context (depth: 2, detail: compact).
3. Scan typography, Auto-Layout constraints, colors, and prototype reactions.
4. Check existing codebase using android-code-indexer to find matching module and contracts.

## Phase 2: Asset Extraction & Token Sync
1. Delegate to figma-asset-extractor subagent.
2. Convert simple vector icons (24-48dp) to res/drawable/ic_<name>.xml via convert_svg_to_android_drawable.
3. Map colors and spacing to AppTheme design tokens in :core:designsystem.
4. Export illustrations/banners directly to assets.

## Phase 3: Contract & Architecture Blueprint
1. Synthesize UI requirements into an Orbit MVI Contract:
   - UiState: Explicit state fields matching visual components.
   - Event / Action: User interaction intents.
   - SideEffect: One-shot navigation and snackbar triggers.
2. Generate Implementation Plan artifact.
3. *(Checkpoint)* Request user sign-off on the plan if ambiguous decisions exist.

## Phase 4: Stateless Compose Implementation
1. Delegate to figma-compose-developer subagent.
2. Implement Stateless Composable in <ScreenName>Screen.kt using AppTheme components.
3. Wire remote artwork via Skydoves Landscapist GlideImage.
4. Implement Preview composables for Light, Dark, and Loading states.
5. Wire ViewModel container (Orbit MVI) and navigation route.

## Phase 5: Quality Gate & Delivery
1. Verify no hardcoded strings or raw hex colors exist.
2. Check Kotlin API design and Orbit MVI conventions.
3. Produce structured change summary artifact.
```

---

## 4. How Antigravity Executes Workflows

Antigravity uses an **asynchronous coordinator-worker model** to execute workflows efficiently without token bloat:

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                             PRIMARY AGENT                                │
│                         (Workflow Coordinator)                           │
│                                                                          │
│  1. Ingests User Prompt & Activates Workflow                             │
│  2. Creates Implementation Plan & Tracks State                           │
│  3. Spawns Specialized Subagents for Heavy Lifting                       │
└────────────┬─────────────────────────────┬───────────────────────────────┘
             │                             │
             ▼                             ▼
┌───────────────────────────┐ ┌────────────────────────────────────────────┐
│   SUBAGENT 1: Research    │ │   SUBAGENT 2: Code Implementation          │
│   (Isolated Context Window)│ │   (Inherited or Specialist Model)          │
│   - Scans files & tokens  │ │   - Generates Composables & MVI Contracts  │
│   - Returns concise JSON  │ │   - Writes drawable XML assets             │
└────────────┬──────────────┘ └────────────┬───────────────────────────────┘
             │                             │
             └──────────────┬──────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         QUALITY GATE & ARTIFACTS                         │
│  - Verifies design token compliance (AppTheme)                           │
│  - Compiles diff summary for developer review                            │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1. Progressive Disclosure
Workflows prevent context window exhaustion. Instead of injecting all project guidelines into every step:
- The coordinator only loads the workflow header.
- Subagents are spawned in **isolated, ephemeral context windows** with only the tools and skills needed for their single phase.
- Subagents return clean, condensed summaries back to the coordinator.

### 2. Checkpoints & Human-in-the-Loop
Workflows can pause for user validation at critical inflection points:
- **Plan Review**: Prompts the user before irreversible codebase refactors.
- **Ambiguity Resolution**: Uses `ask_question` or implementation plan questions to resolve UI or business logic decisions.

### 3. Asynchronous Execution & Non-Blocking Workflow
Long-running phases (like asset batch exports or build verification) run as background tasks (`manage_task` or parallel subagents), allowing the developer to continue reviewing files or chatting without UI freeze.

---

## 5. Ready-to-Use Workflow Templates for This Project

Here are the standard workflow blueprints configured in `.agents/workflows/` for this Android Clean Architecture & Orbit MVI codebase:

### Workflow 1: `figma-to-compose.md`
- **Location:** `.agents/workflows/figma-to-compose.md`
- **Trigger:** Figma URL in chat or `/figma-to-compose`
- **Action:** Inspects Figma node, exports VectorDrawables, maps design tokens to `AppTheme`, writes Stateless Composables, and sets up Orbit MVI contracts.

### Workflow 2: `feature-orbit-mvi.md`
- **Location:** `.agents/workflows/feature-orbit-mvi.md`
- **Trigger:** `/feature-mvi` or "create new feature flow"
- **Action:** Creates feature module scaffolding: `Contract.kt` → `ViewModel.kt` → `UseCase.kt` → `Repository.kt` → `Screen.kt` → `Route.kt`.

### Workflow 3: `code-review.md`
- **Location:** `.agents/workflows/code-review.md`
- **Trigger:** `/code-review` or "review code"
- **Action:** Scans Git diff, audits for over-engineering (Lean philosophy), checks Clean Architecture boundary compliance, and detects hardcoded strings/resources.

---

## 6. Workspace Setup & Git Version Control

Antigravity automatically discovers and indexes custom workflows located under `.agents/workflows/`.

### Git Version Control Best Practice

Antigravity indexes `.agents/` directly to discover rules, skills, agents, and workflows.

> [!IMPORTANT]
> **Do not add `.agents/` to `.gitignore`** if you want workflows and rules shared with your team.  
> If you wish to keep personal workflows machine-local without sharing in Git, add `.agents/` to `.git/info/exclude` instead of `.gitignore`.

---

## 7. Workflow Authoring Checklist

When writing a new workflow in `.agents/workflows/<name>.md`:

- [ ] **Unique Identifier**: Choose a clear, hyphenated name matching its slash command (e.g. `name: figma-to-compose`).
- [ ] **Clear Trigger Spec**: Define explicit keywords and slash commands in YAML frontmatter.
- [ ] **Scoped Skill/Agent Dependencies**: Explicitly list only the necessary subagents and skills to prevent context bloat.
- [ ] **Phase Separation**: Split the task into 3-5 sequential phases with explicit inputs and handoff deliverables.
- [ ] **Verification Gate**: Always end with a quality verification step (e.g. `AppTheme` token check, lint run, or diff summary).
- [ ] **Idempotence**: Ensure the workflow can be safely re-run without duplicating files or breaking existing state.
