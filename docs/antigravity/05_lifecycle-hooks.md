# Lifecycle Hooks (`hooks.json`)

> **Source:** [Google Antigravity Documentation](https://antigravity.google/docs/hooks/)  
> **Topic:** Deterministic Lifecycle Interceptors, Tool Gating, Step Injection, Event Handlers  
> **Target Runtime:** Google Antigravity 2.0, Antigravity CLI & Antigravity IDE  
> **Config Location:** `.agents/hooks.json` (Workspace), `~/.gemini/config/hooks.json` (Global), or `plugins/<name>/hooks.json` (Plugin)

---

## 1. Executive Summary & Architecture

In the **Google Antigravity** platform, **Lifecycle Hooks** provide a deterministic, programmatic intercept layer around the core agent execution loop. While Rules and Skills instruct and guide the Large Language Model (LLM) via prompt engineering and progressive disclosure, Lifecycle Hooks execute external scripts or shell binaries at precise points during execution.

Hooks enable full programmatic control and observability to:
- **Gate and Block Tools**: Intercept dangerous commands (e.g., `rm -rf`, `git push --force`, schema drops) before they run.
- **Mutate Tool Arguments**: Dynamically rewrite tool arguments (e.g., redirecting paths or enforcing flags) via top-level parameter overwrites.
- **Trigger Automated Actions**: Run linters, formatters, or compile checks immediately after file edits.
- **Inject Context & Instructions**: Ephemerally inject system reminders or user messages before the LLM prompt is assembled.
- **Control Loop Termination**: Force the agent loop to continue or stop based on external verification (e.g., pending background tasks, failing test suites).

```text
 ┌────────────────────────────────────────────────────────────────────────────────────────┐
 │                               ANTIGRAVITY AGENT LOOP                                   │
 │                                                                                        │
 │                    ┌──────────────────────────────────────────────┐                    │
 │                    │               User Input / Turn              │                    │
 │                    └──────────────────────┬───────────────────────┘                    │
 │                                           │                                            │
 │                                           ▼                                            │
 │                     ┌───────────────────────────────────────────┐                      │
 │     [HOOK EVENT] ──►│               PreInvocation               │                      │
 │                     │       (Inject ephemeral instructions)     │                      │
 │                     └─────────────────────┬─────────────────────┘                      │
 │                                           │                                            │
 │                                           ▼                                            │
 │                     ┌───────────────────────────────────────────┐                      │
 │                     │          LLM Generation & Planning        │                      │
 │                     └─────────────────────┬─────────────────────┘                      │
 │                                           │                                            │
 │                                           ▼                                            │
 │                     ┌───────────────────────────────────────────┐                      │
 │     [HOOK EVENT] ──►│                PreToolUse                 │◄── (Matcher Regex)   │
 │                     │    (Allow / Deny / Ask / Overwrite Args)  │                      │
 │                     └─────────────────────┬─────────────────────┘                      │
 │                                           │                                            │
 │                                           ▼                                            │
 │                     ┌───────────────────────────────────────────┐                      │
 │                     │              Tool Execution               │                      │
 │                     └─────────────────────┬─────────────────────┘                      │
 │                                           │                                            │
 │                                           ▼                                            │
 │                     ┌───────────────────────────────────────────┐                      │
 │     [HOOK EVENT] ──►│                PostToolUse                │◄── (Matcher Regex)   │
 │                     │     (Linting, auto-format, diagnostics)   │                      │
 │                     └─────────────────────┬─────────────────────┘                      │
 │                                           │                                            │
 │                                           ▼                                            │
 │                     ┌───────────────────────────────────────────┐                      │
 │     [HOOK EVENT] ──►│              PostInvocation               │                      │
 │                     │      (Force continue / terminate loop)    │                      │
 │                     └─────────────────────┬─────────────────────┘                      │
 │                                           │                                            │
 │                                           ▼                                            │
 │                     ┌───────────────────────────────────────────┐                      │
 │     [HOOK EVENT] ──►│                   Stop                    │                      │
 │                     │    (Verify goals met before terminating)  │                      │
 │                     └─────────────────────┬─────────────────────┘                      │
 │                                           │                                            │
 │                                           ▼                                            │
 │                    ┌──────────────────────────────────────────────┐                    │
 │                    │           Turn Finished / Yield UI           │                    │
 │                    └──────────────────────────────────────────────┘                    │
 └────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Configuration & File Anatomy (`hooks.json`)

Lifecycle hooks are declared in a `hooks.json` file. Each top-level key represents a unique **hook profile name**, mapping to its configured lifecycle event handlers.

### Minimal Configuration Example

```json
{
  "code-quality-gate": {
    "enabled": true,
    "PostToolUse": [
      {
        "matcher": "write_to_file|replace_file_content",
        "hooks": [
          {
            "type": "command",
            "command": "./scripts/run-linter.sh",
            "timeout": 15
          }
        ]
      }
    ]
  },
  "command-safety-guard": {
    "enabled": true,
    "PreToolUse": [
      {
        "matcher": "run_command",
        "hooks": [
          {
            "type": "command",
            "command": "python ./scripts/validate_command.py",
            "timeout": 5
          }
        ]
      }
    ]
  },
  "context-reminder": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "./scripts/inject-active-sprint-context.sh"
      }
    ]
  }
}
```

### Top-Level Hook Spec Fields

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `enabled` | `boolean` | No (default: `true`) | Set to `false` to disable all event handlers in this hook profile without deleting its definition. |
| `PreToolUse` | `array` | No | Grouped handlers executed before a tool executes. Requires `matcher` and `hooks` wrapper. |
| `PostToolUse` | `array` | No | Grouped handlers executed after a tool step completes. Requires `matcher` and `hooks` wrapper. |
| `PreInvocation` | `array` | No | Flat list of handlers executed before the LLM is called. |
| `PostInvocation` | `array` | No | Flat list of handlers executed after all tool calls in an invocation finish. |
| `Stop` | `array` | No | Flat list of handlers executed when the agent loop intends to stop. |

> [!NOTE]
> **Merging Semantics**: When multiple hook definitions exist across files or workspace plugins, named hooks for the same event type are merged and executed sequentially in priority order.

---

## 3. Supported Lifecycle Events & Matchers

Antigravity categorizes events into **tool-specific** (grouped with a matcher) and **lifecycle-level** (flat list):

| Event Type | Timing | Matcher Support | Structure | Primary Use Cases |
| :--- | :--- | :--- | :--- | :--- |
| **`PreToolUse`** | Before tool step runs | **Yes** (Tool name) | Grouped (`matcher` + `hooks`) | Guardrails, confirmation prompts, security checks, argument rewriting. |
| **`PostToolUse`** | After tool step runs | **Yes** (Tool name) | Grouped (`matcher` + `hooks`) | Auto-formatting, lint checks, test runs, file audits, diagnostics. |
| **`PreInvocation`** | Before calling LLM | No (N/A) | Flat list of handler objects | Context injection, ephemeral warnings, dynamic sprint parameters. |
| **`PostInvocation`** | After tools finish | No (N/A) | Flat list of handler objects | Output audits, forced loop continuation, step injection. |
| **`Stop`** | When loop terminates | No (N/A) | Flat list of handler objects | Quality verification, blocking premature exit, background sync checks. |

### The Matcher System

For `PreToolUse` and `PostToolUse`, handlers must be wrapped in a group containing a `matcher` regular expression string:

```json
{
  "PreToolUse": [
    {
      "matcher": "run_command|write_to_file",
      "hooks": [
        {
          "command": "./scripts/audit_tool.sh"
        }
      ]
    }
  ]
}
```

#### Matcher Patterns:
- `"*"` or `""` — Matches **all** tools.
- `"run_command"` — Matches exactly the `run_command` tool.
- `"write_to_file|replace_file_content"` — Matches file writing or editing tools.
- `"browser_.*"` — Matches all browser automation tools (e.g. `browser_click`, `browser_navigate`).
- `"figma_.*"` — Matches all Figma MCP tools.

> [!TIP]
> Tool names are derived by converting the internal step type to lowercase and stripping the `CORTEX_STEP_TYPE_` prefix (e.g., `CORTEX_STEP_TYPE_RUN_COMMAND` $\rightarrow$ `run_command`).

---

## 4. Hook Handler Specification & Execution Runtime

Every individual handler in a `hooks` array conforms to the following schema:

```json
{
  "type": "command",
  "command": "./scripts/verify.sh",
  "timeout": 30
}
```

### Handler Fields

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `type` | `string` | `"command"` | Execution type. Currently, `"command"` (shell execution) is supported. |
| `command` | `string` | **Required** | The command to execute via shell (`sh -c` on Unix/Linux/macOS, `cmd /c` on Windows). |
| `timeout` | `integer` | `30` | Execution timeout in seconds before the hook process is terminated. |

### Runtime Environment & Path Resolution

- **Current Working Directory (CWD)**: Set to the directory containing `hooks.json` (e.g., the workspace root or `.agents/`).
- **Tilde Expansion**: `~` is automatically expanded to the user's home directory.
- **Execution Mode**: Synchronous and blocking. The agent loop pauses until the hook exits and returns its stdout JSON.

---

## 5. JSON Communication Protocol (STDIN & STDOUT)

Hooks communicate with Antigravity via standard I/O:
- **Context input** is provided as a JSON payload on **`stdin`**.
- **Results / directives** must be written as a valid JSON object to **`stdout`**.

> [!IMPORTANT]
> All JSON keys in the hook payloads use **`camelCase`** (protojson encoding), e.g., `conversationId`, `workspacePaths`, `stepIdx`, `toolCall`.

### Common Input Payload (All Events)

Every hook payload passed to `stdin` includes common metadata:

```json
{
  "conversationId": "3dcfd159-63a7-4387-8259-18ab0eb301f0",
  "workspacePaths": [
    "/home/user/projects/my-app"
  ],
  "transcriptPath": "/home/user/projects/my-app/.gemini/antigravity/transcript.jsonl",
  "artifactDirectoryPath": "/home/user/projects/my-app/.gemini/antigravity/artifacts",
  "modelName": "gemini-3.7-flash"
}
```

> [!NOTE]
> `transcriptPath` and `artifactDirectoryPath` vary based on the surface interface:
> - **Antigravity CLI**: `~/.gemini/antigravity-cli/...`
> - **Antigravity 2.0**: `~/.gemini/antigravity/...`
> - **Antigravity IDE**: `~/.gemini/antigravity-ide/...`

---

### Detailed Event Contracts

### 1. `PreToolUse` Contract

Fired immediately before a tool is executed. Use to permit, deny, confirm, or mutate arguments.

#### Input Payload (`stdin`):
```json
{
  "toolCall": {
    "name": "run_command",
    "args": {
      "CommandLine": "rm -rf /build/cache",
      "Cwd": "/home/user/projects/my-app"
    }
  },
  "stepIdx": 14,
  "conversationId": "3dcfd159-63a7-4387-8259-18ab0eb301f0",
  "workspacePaths": ["/home/user/projects/my-app"],
  "transcriptPath": "/home/user/projects/my-app/.gemini/antigravity/transcript.jsonl",
  "artifactDirectoryPath": "/home/user/projects/my-app/.gemini/antigravity/artifacts",
  "modelName": "gemini-3.7-flash"
}
```

#### Output Directives (`stdout`):
```json
{
  "decision": "ask",
  "reason": "Potentially destructive file deletion detected.",
  "permissionOverrides": ["command(rm -rf /build/cache)"],
  "overwrite": {
    "CommandLine": "rm -rf ./build/cache"
  }
}
```

#### Output Schema Fields:
- **`decision`** (`string`, **required**):
  - `"allow"`: Automatically permits tool execution without prompting.
  - `"deny"`: Hard blocks tool execution immediately with the supplied `reason`.
  - `"ask"`: Prompts the user with a confirmation modal (respects cached "Always Allow" decisions).
  - `"force_ask"`: Always prompts the user, bypassing any cached permissions.
- **`reason`** (`string`, optional): Explanation displayed to the user in confirmation dialogs or returned to the agent if denied.
- **`permissionOverrides`** (`array<string>`, optional): List of permission strings to grant for this turn.
- **`overwrite`** (`object`, optional): Top-level shallow merge into `toolCall.args`. Values in this object replace the original arguments before execution.

---

### 2. `PostToolUse` Contract

Fired immediately after a tool finishes execution. Use for formatting, verification, or test triggers.

#### Input Payload (`stdin`):
```json
{
  "stepIdx": 14,
  "error": "",
  "conversationId": "3dcfd159-63a7-4387-8259-18ab0eb301f0",
  "workspacePaths": ["/home/user/projects/my-app"],
  "transcriptPath": "/home/user/projects/my-app/.gemini/antigravity/transcript.jsonl",
  "artifactDirectoryPath": "/home/user/projects/my-app/.gemini/antigravity/artifacts",
  "modelName": "gemini-3.7-flash"
}
```

*Note: `error` will contain the error string if the tool step failed.*

#### Output Directives (`stdout`):
```json
{}
```
*Expects a valid empty JSON object `{}`.*

---

### 3. `PreInvocation` Contract

Fired before a prompt is sent to the LLM. Use to dynamically insert ephemeral system guidance or user instructions.

#### Input Payload (`stdin`):
```json
{
  "invocationNum": 2,
  "initialNumSteps": 8,
  "conversationId": "3dcfd159-63a7-4387-8259-18ab0eb301f0",
  "workspacePaths": ["/home/user/projects/my-app"],
  "transcriptPath": "/home/user/projects/my-app/.gemini/antigravity/transcript.jsonl",
  "artifactDirectoryPath": "/home/user/projects/my-app/.gemini/antigravity/artifacts",
  "modelName": "gemini-3.7-flash"
}
```

#### Output Directives (`stdout`):
```json
{
  "injectSteps": [
    {
      "ephemeralMessage": "Notice: The database schema was migrated in step 4. Ensure all queries reference the updated column names."
    }
  ]
}
```

#### Step Types for `injectSteps`:
- `{"ephemeralMessage": "..."}` — Injects a transient system notification.
- `{"userMessage": "..."}` — Injects a message formatted as user input.
- `{"toolCall": {"name": "...", "args": {...}}}` — Injects a synthetic tool call into context.

---

### 4. `PostInvocation` Contract

Fired after the LLM completes an invocation turn and all generated tool calls have concluded.

#### Input Payload (`stdin`):
*Same structure as `PreInvocation` input.*

#### Output Directives (`stdout`):
```json
{
  "injectSteps": [],
  "terminationBehavior": "force_continue"
}
```

#### Output Fields:
- **`injectSteps`** (`array`, optional): Steps to inject into the transcript.
- **`terminationBehavior`** (`string`, optional):
  - `"force_continue"`: Bypasses model stop tokens and forces another invocation loop turn.
  - `"terminate"`: Immediately halts the agent loop.
  - `""` (omitted): Normal agent loop behavior.

---

### 5. `Stop` Contract

Fired when the agent decides to conclude its task and exit the execution loop. Use as a final quality verification gate.

#### Input Payload (`stdin`):
```json
{
  "executionNum": 1,
  "terminationReason": "model_stop",
  "error": "",
  "fullyIdle": true,
  "conversationId": "3dcfd159-63a7-4387-8259-18ab0eb301f0",
  "workspacePaths": ["/home/user/projects/my-app"],
  "transcriptPath": "/home/user/projects/my-app/.gemini/antigravity/transcript.jsonl",
  "artifactDirectoryPath": "/home/user/projects/my-app/.gemini/antigravity/artifacts",
  "modelName": "gemini-3.7-flash"
}
```

#### Output Directives (`stdout`):
```json
{
  "decision": "continue",
  "reason": "Build verification failed: 2 unit tests are failing. Please fix them before finishing."
}
```

#### Output Fields:
- **`decision`** (`string`, **required**):
  - `"continue"`: Blocks the stop request and re-enters the agent loop with `reason` injected as a feedback prompt.
  - Any other value (or omitted): Permits the agent to stop normally.
- **`reason`** (`string`, optional): System feedback message presented to the agent upon continuation.

---

## 6. Practical Real-World Recipes & Patterns

### Recipe 1: Destructive Command Safety Guard (`PreToolUse`)

Intercept `run_command` and block dangerous commands or require explicit user confirmation.

#### 1. Configuration in `.agents/hooks.json`:
```json
{
  "security-guard": {
    "PreToolUse": [
      {
        "matcher": "run_command",
        "hooks": [
          {
            "type": "command",
            "command": "python3 scripts/security_guard.py"
          }
        ]
      }
    ]
  }
}
```

#### 2. Handler Script (`scripts/security_guard.py`):
```python
#!/usr/bin/env python3
import sys
import json
import re

DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+[/~]",
    r"git\s+push\s+.*--force",
    r"drop\s+database",
    r":(){ :|:& };:"
]

def main():
    try:
        data = json.load(sys.stdin)
        tool_call = data.get("toolCall", {})
        command = tool_call.get("args", {}).get("CommandLine", "")

        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                response = {
                    "decision": "deny",
                    "reason": f"Security policy violation: dangerous command detected matching '{pattern}'."
                }
                print(json.dumps(response))
                return

        # Commands modifying Git branches require manual user approval
        if "git checkout" in command or "git reset" in command:
            response = {
                "decision": "force_ask",
                "reason": f"Branch state modification requires explicit user confirmation: {command}"
            }
            print(json.dumps(response))
            return

        # Otherwise allow
        print(json.dumps({"decision": "allow"}))
    except Exception as e:
        # Fallback to asking user on script failure
        print(json.dumps({"decision": "ask", "reason": f"Security hook error: {str(e)}"}))

if __name__ == "__main__":
    main()
```

---

### Recipe 2: Auto-Formatting & Linting on Save (`PostToolUse`)

Automatically format code files whenever `write_to_file` or `replace_file_content` completes.

#### 1. Configuration in `.agents/hooks.json`:
```json
{
  "auto-formatter": {
    "PostToolUse": [
      {
        "matcher": "write_to_file|replace_file_content",
        "hooks": [
          {
            "type": "command",
            "command": "bash scripts/format_code.sh",
            "timeout": 20
          }
        ]
      }
    ]
  }
}
```

#### 2. Handler Script (`scripts/format_code.sh`):
```bash
#!/usr/bin/env bash
# Read stdin JSON (discard or parse if specific file targets are needed)
cat > /dev/null

# Run project linters and formatters silently
if [ -f "gradlew" ]; then
  ./gradlew spotlessApply --quiet 2>/dev/null || true
elif [ -f "package.json" ]; then
  npx prettier --write "src/**/*.{ts,tsx,js,json}" --log-level error 2>/dev/null || true
fi

# Always return empty JSON object
echo "{}"
```

---

### Recipe 3: Argument Rewriting & Sandbox Redirection (`PreToolUse`)

Rewrite tool arguments on the fly using `overwrite` (e.g., redirecting temporary file writes to a sandbox).

#### 1. Configuration in `.agents/hooks.json`:
```json
{
  "sandbox-redirector": {
    "PreToolUse": [
      {
        "matcher": "write_to_file",
        "hooks": [
          {
            "type": "command",
            "command": "python3 scripts/sandbox_redirect.py"
          }
        ]
      }
    ]
  }
}
```

#### 2. Handler Script (`scripts/sandbox_redirect.py`):
```python
#!/usr/bin/env python3
import sys
import json

def main():
    payload = json.load(sys.stdin)
    args = payload.get("toolCall", {}).get("args", {})
    target_file = args.get("TargetFile", "")

    # Prevent direct modification of production config
    if target_file.endswith("prod_config.env"):
        response = {
            "decision": "allow",
            "overwrite": {
                "TargetFile": target_file.replace("prod_config.env", "dev_config.env")
            },
            "reason": "Redirected write from production config to development sandbox."
        }
        print(json.dumps(response))
        return

    print(json.dumps({"decision": "allow"}))

if __name__ == "__main__":
    main()
```

---

### Recipe 4: Test Verification Quality Gate on Stop (`Stop`)

Ensure the test suite passes before the agent is permitted to stop working.

#### 1. Configuration in `.agents/hooks.json`:
```json
{
  "stop-verifier": {
    "Stop": [
      {
        "type": "command",
        "command": "python3 scripts/verify_stop.py",
        "timeout": 60
      }
    ]
  }
}
```

#### 2. Handler Script (`scripts/verify_stop.py`):
```python
#!/usr/bin/env python3
import sys
import json
import subprocess

def main():
    payload = json.load(sys.stdin)
    
    # Don't loop infinitely if max steps exceeded or error occurred
    if payload.get("terminationReason") in ["max_steps_exceeded", "error"]:
        print(json.dumps({"decision": "stop"}))
        return

    # Run the test suite
    result = subprocess.run(["npm", "test"], capture_output=True, text=True)
    
    if result.returncode != 0:
        response = {
            "decision": "continue",
            "reason": f"Unit tests failed with exit code {result.returncode}.\nOutput:\n{result.stderr[-500:]}\nPlease fix failing tests before finishing."
        }
        print(json.dumps(response))
    else:
        print(json.dumps({"decision": "stop"}))

if __name__ == "__main__":
    main()
```

---

## 7. Discovery, Precedence & Plugins

Antigravity resolves lifecycle hooks from multiple locations according to the following precedence hierarchy (highest priority to lowest):

1. **Workspace Root**: `<workspace_root>/.agents/hooks.json` (or `.agent/hooks.json`)
2. **Workspace Plugins**: Declared in `plugins/<plugin_name>/hooks.json`
3. **User-Global Config**: `~/.gemini/config/hooks.json` (or `~/.gemini/antigravity/hooks.json`)

### Sequential Merging Order

When multiple hook files declare handlers for the same lifecycle event:
- Handlers are executed in **descending order of priority** (Workspace $\rightarrow$ Plugins $\rightarrow$ Global).
- In `PreToolUse`, if any hook returns `"deny"`, execution is immediately blocked and subsequent hooks for that event are skipped.
- In `PreToolUse`, if any hook returns `"force_ask"`, it takes precedence over `"ask"` or `"allow"`.

---

## 8. Best Practices & Performance Guidelines

1. **Keep Hook Scripts Fast & Non-Blocking**:
   - Because hooks run synchronously on the agent loop thread, long-running operations (>10s) will degrade responsiveness. Set explicit `timeout` values on all handler definitions.
2. **Ensure Idempotency**:
   - Handlers on `PostToolUse` and `PreToolUse` should be idempotent to avoid cascading side-effects during multi-step tool calls.
3. **Always Output Valid JSON**:
   - Every hook script must output a valid JSON object to `stdout` under all circumstances (including exception paths), or the agent loop will treat the output as a parse failure.
4. **Use Stderr for Debug Logs**:
   - Any log messages or debugging output generated by your hook scripts should be redirected to `stderr` (`sys.stderr.write(...)` or `>&2`). `stdout` must remain exclusively reserved for JSON responses.
5. **Check `enabled` for Easy Toggling**:
   - Use `"enabled": false` to disable specific hook profiles during active debugging rather than removing configuration blocks.

---

### Sources & References
- [Google Antigravity Docs: Lifecycle Hooks](https://antigravity.google/docs/hooks/)
- [Antigravity Customization Architecture & Skills](https://antigravity.google/docs/skills/)
- [Antigravity Agent Workflows & Pipelines](https://antigravity.google/docs/agent-workflows/)
