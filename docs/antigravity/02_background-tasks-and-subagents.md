# Background Tasks & Subagents

> **Source:** [Google Antigravity CLI Docs](https://antigravity.google/docs/cli/subagents/)  
> **Topic:** Antigravity CLI / Asynchronous Agent Execution & Background Operations

---

Delegate slow builds, multi-file code generation, and research sweeps to parallel background agents while maintaining your active programming flow.

> [!NOTE]
> **Antigravity 2.0 & Hub Docs:** For core platform capabilities, subagent lifecycle state diagrams, inter-agent messaging, and nesting depth limits, see the Antigravity 2.0 Subagents Documentation (`/docs/subagents`).

---

## Asynchronous Execution Model

To maximize developer velocity, Antigravity CLI leverages a multi-threaded asynchronous execution architecture. Instead of locking your terminal session during long-running builds, massive codebase search sweeps, or complex multi-file edits, the primary agent delegates these operations to parallel **Subagents** or background **Tasks**.

This delegation model ensures you never have to wait on high-latency AI processes. You can continue drafting code, submitting prompts, or inspecting files while multiple autonomous background threads execute validation tasks in parallel.

---

## Managing Agents: The `/agents` Panel

The active agent hierarchy and custom agent selection menu are fully transparent and manageable through the interactive **Agent Manager Panel** (`/agents`).

### Opening the Panel

Type `/agents` in the CLI prompt and press `Enter` to open the interactive panel:

```bash
/agents
```

### Panel Overview

The panel displays a live checklist of all active, completed, killed, or failed background agents:

- **Identifier**: The unique target subagent ID.
- **Role**: The specialized role of the agent (such as "Codebase Researcher" or "Database Debugger").
- **State**: Live status indicators (`running`, `done`, `killed`, or `error`).
- **Step**: A real-time summary of the tool or reasoning step currently being executed.

> [!TIP]
> You can also select and switch between custom agents (or fork conversations) from this panel.

---

## Custom Agents (Markdown Format)

In addition to built-in agents, the CLI automatically discovers custom agents defined in Markdown format (`.md`) with YAML frontmatter:

- **Workspace Agents**: `.agents/agents/<name>.md` or `.agents/agents/<name>/agent.md`
- **Global Agents**: `~/.gemini/config/agents/`

When a custom agent has `subagent: true` set in its YAML frontmatter, the primary agent can invoke it via `invoke_subagent`. You can also select custom agents directly as your primary agent in the `/agents` panel menu.

---

## Deep-Dive Monitoring

To inspect the inner reasoning, thoughts, and logs of a specific background agent:

1. Open the `/agents` panel and highlight the target agent using `↑` / `↓`.
2. Press `Enter` to open the **Subagent Detail View**.
3. Inspect the subagent's entire reasoning log, including its private internal thoughts, tool calls, and execution outputs.
4. Press `Esc` to exit and return to the main Agent Manager list.

---

## Monitoring Background Tasks with `/tasks`

For non-agentic background operations, such as direct shell commands, testing suites, or simple background queries initiated via `/btw`, use the `/tasks` command:

```bash
/tasks
```

The tasks tracking list lets you:

- Track standard non-interactive background processes.
- Select a task using `↑` / `↓` and press `Enter` to view stdout logs.
- Terminate runaway terminal processes safely.

---

## Keyboard Ergonomics

To reduce context-switching friction when subagents require manual interaction or tool authorizations, Antigravity CLI integrates high-efficiency shortcut paths:

### 1. Detailed "Teleport" Navigation (`Alt+J`)

When a subagent encounters a tool requiring approval (e.g. writing a file or running a database migration), a status bar notification blinks:

- Press `Alt+J` inside the main prompt panel to instantly "teleport" from your current conversation directly into the Detail View of the next subagent awaiting approval.
- Confirm or reject the action, then press `Esc` to teleport back to your primary thread.

### 2. "Fast-Path" Confirmations (`Ctrl+K`)

To authorize an agent action instantly without leaving your active workspace:

- Check the inline status notification displayed right above your active prompt box (e.g., `Subagent 12 asks to run "npm test"`).
- Press `Ctrl+K` to instantly approve the pending fast-path action without switching panels or opening overlays.

---

## Related Guides & Configuration

- **Settings, Rendering & Keybindings**: Customize key maps, buffering, and JSON rules.
- **Permissions & Sandbox**: Enforce security containment rings on background processes.
- **Plugins & Skills**: Create custom skills and slash commands.
