# Status Line Customization

> **Source:** [Google Antigravity Docs](https://antigravity.google/docs/cli/statusline/)  
> **Topic:** Antigravity CLI / Custom Status Line Scripting & JSON Payload

---

Define custom scripting configurations and format dynamic JSON state payloads to customize your TUI status line.

> [!NOTE]
> **Status Line Command:** To toggle the status line on/off or configure it interactively from the TUI, see the **Status Line Command** (`/statusline`).

---

## Overview

The status line is positioned at the bottom of the TUI prompt panel. It provides at-a-glance context regarding:
- Active agent cycles and states (`idle`, `thinking`, `working`, `tool_use`, `initializing`).
- Workspace environments and current directory.
- Context window token consumption and remaining percentage.
- Background execution tasks and subagent status.

---

## Custom Status Line Scripting

For advanced terminal layouts or custom status bar displays, you can route active agent metadata into a custom script.

### Configuration

Add a `statusLine` configuration block to your `~/.gemini/antigravity-cli/settings.json` file:

```json
{
    "statusLine": {
        "type": "command",
        "command": "~/.gemini/antigravity-cli/statusline.sh"
    }
}
```

### Execution Model

Whenever the agent state changes, the TUI:
1. Executes your command script.
2. Pipes a detailed state JSON payload directly to the script's `stdin`.
3. Reads your formatted string from `stdout`.
4. Renders the result in the prompt's status line. Full ANSI color codes are supported.

### Optional Configuration Keys

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `type` | string | `"command"` | Execution type for status line script. |
| `command` | string | — | Path to the executable script or command. |
| `padding` | int | `0` | Adds blank lines above the status line for visual breathing room. |
| `enabled` | boolean | `true` | Set to `false` to suspend the script while keeping the command on file. |
| `stack_with_default` | boolean | `false` | Set to `true` to render your custom script output below the built-in status line instead of replacing it. |

---

## Available JSON Fields

The JSON payload piped to your script's `stdin` contains the following top-level fields:

| Field | Type | Description |
| :--- | :--- | :--- |
| `cwd` | `string` | Current working directory when the CLI was launched. |
| `session_id` | `string` | Backward-compatibility alias for `conversation_id`. |
| `conversation_id` | `string` | Current unique conversation ID. |
| `transcript_path` | `string` | Absolute path to the active conversation transcript log file (optional). |
| `model` | `object` | Contains `id` and `display_name` of the active model. |
| `workspace` | `object` | Contains `current_dir` and `project_dir` paths. |
| `version` | `string` | CLI version string. |
| `context_window` | `object` | Token usage details: `total_input_tokens`, `total_output_tokens`, `context_window_size`, `used_percentage`, `remaining_percentage`, and `current_usage`. |
| `exceeds_200k_tokens` | `bool` | `true` if the conversation context has exceeded 200k tokens (`null` before first API call). |
| `product` | `string` | Application name (e.g., `antigravity`). |
| `quota` | `object` | Maps model/bucket IDs to quota status: `remaining_fraction`, `reset_time`, `reset_in_seconds` (optional). |
| `agent_state` | `string` | Current agent state: `idle`, `thinking`, `working`, `tool_use`, `initializing`. |
| `vcs` | `object` | Version control info: `type` (`git`/`jj`/`hg`), `branch`, `client`, `dirty` (optional). |
| `sandbox` | `object` | Sandbox configuration: `enabled`, `allow_network` (optional). |
| `artifact_count` | `int` | Number of artifacts produced in the active conversation. |
| `plan_tier` | `string` | Subscription tier of the authenticated user (optional). |
| `email` | `string` | Email / LDAP of the authenticated user. |
| `pending_input_count` | `int` | Number of queued user messages waiting to be processed. |
| `tool_confirmation_pending` | `bool` | `true` when a tool confirmation approval dialog is showing. |
| `task_count` | `int` | Number of currently running background tasks. |
| `terminal_width` | `int` | Live character width of the interactive terminal. |
| `execution_mode` | `string` | Current active prompt execution mode (e.g., `planning`, `fast`). |
| `vim` | `object` | Vim editing state: `mode` is `NORMAL`, `INSERT`, `VISUAL`, or `VISUAL LINE` (present only when Vim mode is enabled). |

---

## JSON Payload Example

Here is a typical sanitized JSON payload piped to your status line script:

```json
{
    "cwd": "/home/user/my-project",
    "session_id": "12345678-abcd-ef01-2345-6789abcdef01",
    "conversation_id": "12345678-abcd-ef01-2345-6789abcdef01",
    "transcript_path": "/home/user/.gemini/antigravity/brain/12345678-abcd-ef01-2345-6789abcdef01/.system_generated/logs/transcript.jsonl",
    "model": {
        "id": "Gemini 3.5 Flash (High)",
        "display_name": "Gemini 3.5 Flash (High)"
    },
    "workspace": {
        "current_dir": "/home/user/my-project",
        "project_dir": "/home/user/my-project"
    },
    "version": "1.0.13",
    "context_window": {
        "total_input_tokens": 88244,
        "total_output_tokens": 61074,
        "context_window_size": 1048576,
        "used_percentage": 14.24,
        "remaining_percentage": 85.76,
        "current_usage": {
            "input_tokens": 63382,
            "output_tokens": 346,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 20857
        }
    },
    "exceeds_200k_tokens": false,
    "product": "antigravity",
    "quota": {
        "gemini-weekly": {
            "remaining_fraction": 0.9378,
            "reset_time": "2026-07-06T07:50:32Z",
            "reset_in_seconds": 560580
        }
    },
    "agent_state": "idle",
    "vcs": {
        "type": "git",
        "branch": "main",
        "dirty": false
    },
    "sandbox": {
        "enabled": false
    },
    "artifact_count": 2,
    "plan_tier": "Pro",
    "email": "developer@email.com",
    "task_count": 1,
    "terminal_width": 111,
    "execution_mode": "planning"
}
```

---

## Example Script & Setup

You can download a complete, layout-adaptive script from the official [statusline.sh example on GitHub](https://github.com/google-antigravity/antigravity-cli/blob/main/examples/statusline/statusline.sh). This script renders state badges, handles active git branches, and formats context window progress bars dynamically.

1. Save the script to `~/.gemini/antigravity-cli/statusline.sh`
2. Make it executable:
   ```bash
   chmod +x ~/.gemini/antigravity-cli/statusline.sh
   ```

---

## See Also

- **Status Line Command (`/statusline`)**: Toggle status line elements interactively.
- **Terminal Title Customization (`/docs/cli/title`)**: Configure dynamic terminal window titles.
- **Settings, Rendering & Keybindings (`/docs/cli/settings`)**: Customize keyboard hotkeys, rendering, and buffers.
- **Permissions & Sandbox (`/docs/cli/sandbox`)**: Manage secure execution policies and directory permissions.
