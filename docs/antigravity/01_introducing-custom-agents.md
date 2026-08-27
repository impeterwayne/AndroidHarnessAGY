# Introducing Custom Agents

> **Source:** [Google Antigravity Blog](https://antigravity.google/blog/introducing-custom-agents)  
> **Author:** The Antigravity Team  
> **Date:** August 12, 2026

---

Software engineering has shifted from writing lines of code to orchestrating agents. With this shift comes an opportunity for a real productivity unlock via division of labor, breaking complex projects down into specialized agents that can act, verify, and run tasks in parallel.

This is why we are introducing **Custom Agents** with first-class support in Antigravity 2.0 and the Antigravity CLI, with the Antigravity IDE following shortly.

This document details what custom agents are, how you can set one up in seconds, and key features given to custom agents that are unique to Antigravity.

---

## What are custom agents and why do they matter?

General-purpose coding assistants are great, but they suffer from two major limitations:

1. **Lack of Specialization**: A general-purpose assistant doesn't know your specific project's testing conventions or dependency management rules unless you explain them every single time.
2. **Context Window Bloat**: Loading a massive, monolithic prompt containing all your coding guidelines, linters, and testing rules into every single chat turns into a token budget disaster.

Custom agents solve this. They are specialized, file-based configurations that define a particular role with its own scoped instructions, tools, and constraints. This keeps your active context clean, minimizes token overhead, and gives you a predictable partner for specific tasks.

### Relation to Skills and Dynamic Subagents

Custom agents don't replace skills and dynamic subagents; they simply provide even more customizability for another level of optimization:

- **Skills** specialize a custom agent by providing additional context and domain instructions. Through progressive discovery, skills help address context window bloat by omitting complete instructions from the prompt by default until needed. However, across an entire organization or large project, loading all skill descriptions can still take up valuable context. Custom agents let you specify the exact subset of skills, MCP servers, and hooks relevant for the specialization at hand. Additionally, custom agents let you customize system instructions, default tools, and core agent loop parameters.
- **Dynamic Subagents** allow the main coordinator agent to delegate isolated tasks to subagents without polluting the primary context. Custom agents take this further by allowing delegation to a named, pre-configured agent with explicit model, permissions, and tool configurations.

---

## What's available today in Antigravity 2.0 & CLI

Custom agents are fully integrated across both the visual **Antigravity 2.0 Desktop App** and the **Antigravity CLI**.

Similar to Skills, custom agents use a Markdown file format (`.md`) containing a YAML frontmatter header. You save these files in your local workspace or user-globally:

- **Workspace Agents**: `.agents/agents/` (e.g., `.agents/agents/<name>.md` or `.agents/agents/<name>/agent.md`)
- **Global Agents**: `~/.gemini/config/agents/`

Committing project-specific agents to `.agents/agents/` makes them automatically available to every teammate who checks out the repository—giving your entire team standardized, instant workflow assistants out of the box without requiring manual setup.

### 101 Blueprint Example

```markdown
---
name: dependency-modernizer
description: Helps upgrade local packages and verify that project tests pass.
model: flash
tools:
  - view_file
  - replace_file_content
  - manage_task
  - run_command
---

# Core Instructions
You are a dependency modernizer. Your job is to check configuration files,
update target dependencies, run test suites, and verify the build passes.
```

Creating a specialized agent requires only a single Markdown file. The frontmatter configures how the agent runs, and the markdown body compiles directly into its system prompt.

---

## What makes Antigravity custom agents special?

Antigravity introduces several key architectural advantages for custom agents:

### 1. True Symmetry: Main Agent vs. Subagent

In many existing agent tools, custom agents are restricted to being **subagents only**. You interact with a default main agent, and it decides when to spawn worker subagents behind the scenes.

Antigravity introduces **execution symmetry** via simple configuration flags:

```yaml
# Add these to the YAML frontmatter:
mainAgent: true
subagent: true
```

- **As a Main Agent**: Select the custom agent directly from the dropdown in the Antigravity 2.0 GUI, or run it via the CLI:
  ```bash
  agy --agent dependency-modernizer
  ```
  The specific instructions compile into the primary system prompt with full session control.
- **As a Subagent**: The same agent can be dynamically called via the `invoke_subagent` tool by a coordinator agent.

### 2. Scoped Safety Policies (`commandExecutionPolicy`)

Running an agent that executes command-line operations (like dependency installs or test suites) can be frustrating if permissions are either too loose (security risk) or too strict (constant approval prompts).

Antigravity adds a dedicated execution filter:

```yaml
# Add this to the YAML frontmatter:
permissionMode: acceptEdits
commandExecutionPolicy: auto
```

Setting `commandExecutionPolicy: auto` allows the agent to execute standard test and compilation commands autonomously in the background. High-risk commands (such as deleting files or destructive operations) remain strictly gated behind manual approvals.

### 3. Curated Skills & Scoped Toolsets (`skills` & `tools`)

Generalist assistants often suffer from tool confusion and context bloat when equipped with dozens of tools, MCP servers, and global workspace guidelines simultaneously.

Antigravity custom agents let you explicitly define the exact subset of tools and domain skills available:

```yaml
# Add these to the YAML frontmatter:
tools:
  - view_file
  - replace_file_content
  - run_command
skills:
  - skills/package-upgrade-rules
```

Instead of polluting your context window with every skill and MCP tool registered across your entire workspace, the custom agent only receives assets relevant to its specialization, helping the agent stay laser-focused on the task.
