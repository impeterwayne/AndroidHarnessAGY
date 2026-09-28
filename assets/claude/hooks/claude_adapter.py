#!/usr/bin/env python3
"""
Claude Code -> Antigravity hook adapter.

The hook scripts beside this file were written against Antigravity's hook contract
(`toolCall.args`, `conversationId`, `{"decision": ...}` verdicts, CWD = the harness
dir). Claude Code speaks a different one. Rather than fork seven scripts, `aha init
--platform claude` wires every hook through this file, which translates the payload
in, runs the unchanged script in-process, and translates the verdict out.

    claude_adapter.py <ClaudeEvent> <script.py> [script args...]
    claude_adapter.py SessionStart

Mapping:
  PreToolUse        Write/Edit/MultiEdit -> write_to_file/replace_file_content args,
                    Bash -> run_command {CommandLine}. `deny` becomes
                    permissionDecision deny; an `overwrite` of CommandLine becomes
                    updatedInput. Pass verdicts ("ask"/"allow") defer to Claude's own
                    permission flow -- auto-approving every write or shell command
                    because a lint passed would be a policy change, not a port.
  UserPromptSubmit  intent_gate matches the prompt text directly (Antigravity had to
                    dig it out of the transcript); other scripts run as PreInvocation.
  Stop/SubagentStop `{"decision":"continue"}` becomes `{"decision":"block"}`.
  SessionStart      exports AGY_CONVERSATION_ID = session_id through CLAUDE_ENV_FILE so
                    loop.py names its ledger after the session the Stop gate sees.

Subagent calls carry `agent_type` (and `agent_id`); that is how write_guard tells the
root session from a delegate here, instead of scanning Antigravity's brain dirs.

Fails open on every error: prints `{}` and exits 0.
"""

from __future__ import annotations

import io
import json
import os
import re
import runpy
import sys
from pathlib import Path

# A Claude install is committed, so in-process imports must not litter __pycache__.
sys.dont_write_bytecode = True

HOOKS_DIR = Path(__file__).resolve().parent
HARNESS_DIR = HOOKS_DIR.parent

TOOL_NAMES = {
    "view_file": "Read",
    "write_to_file": "Write",
    "multi_replace_file_content": "Edit",
    "replace_file_content": "Edit",
    "grep_search": "Grep",
    "list_dir": "Glob",
    "run_command": "Bash",
    "invoke_subagent": "Agent",
    "send_message": "SendMessage",
    "manage_subagents": "background agents",
}
TOOL_RE = re.compile(r"\b(" + "|".join(TOOL_NAMES) + r")\b")


def claudeify(text: str) -> str:
    """Rename Antigravity tools in prose the agent will read."""
    text = text.replace("TypeName=", "subagent_type=")
    return TOOL_RE.sub(lambda m: TOOL_NAMES[m.group(1)], text)


def conversation_id(payload: dict) -> str:
    """One id per agent: subagents get their own, so refcounted Stops stay balanced."""
    session = payload.get("session_id") or ""
    if payload.get("agent_id"):
        return str(payload["agent_id"])
    if payload.get("agent_type"):
        return f"{session}-{payload['agent_type']}"
    return session


def is_subagent(payload: dict) -> bool:
    return bool(payload.get("agent_id") or payload.get("agent_type"))


def tool_call(payload: dict) -> dict:
    name = payload.get("tool_name") or ""
    inp = payload.get("tool_input") or {}
    if name == "Write":
        return {"name": "write_to_file",
                "args": {"TargetFile": inp.get("file_path"), "CodeContent": inp.get("content", "")}}
    if name == "Edit":
        return {"name": "replace_file_content",
                "args": {"TargetFile": inp.get("file_path"),
                         "ReplacementContent": inp.get("new_string", "")}}
    if name == "MultiEdit":
        edits = inp.get("edits") or []
        return {"name": "multi_replace_file_content",
                "args": {"TargetFile": inp.get("file_path"),
                         "ReplacementContent": "\n".join(e.get("new_string", "") for e in edits)}}
    if name == "Bash":
        return {"name": "run_command", "args": {"CommandLine": inp.get("command", "")}}
    return {"name": name, "args": inp}


def agy_payload(payload: dict, event: str) -> dict:
    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or str(HARNESS_DIR.parent)
    out = {
        "conversationId": conversation_id(payload),
        "transcriptPath": payload.get("transcript_path"),
        "workspacePaths": [project],
    }
    if event == "PreToolUse":
        out["toolCall"] = tool_call(payload)
    if event in ("Stop", "SubagentStop"):
        out["terminationReason"] = "NO_TOOL_CALL"
        out["fullyIdle"] = True
    return out


def run_script(script: str, args: list[str], stdin_payload: dict) -> dict:
    """Run a hook script in-process with CWD = harness dir, as Antigravity would."""
    saved = sys.argv, sys.stdin, sys.stdout, os.getcwd()
    path = HOOKS_DIR / script
    sys.argv = [str(path), *args]
    sys.stdin = io.StringIO(json.dumps(stdin_payload))
    sys.stdout = io.StringIO()
    try:
        os.chdir(HARNESS_DIR)
        try:
            runpy.run_path(str(path), run_name="__main__")
        except SystemExit:
            pass
        text = sys.stdout.getvalue().strip().splitlines()
    finally:
        sys.argv, sys.stdin, sys.stdout = saved[0], saved[1], saved[2]
        os.chdir(saved[3])
    try:
        return json.loads(text[-1]) if text else {}
    except ValueError:
        return {}


def on_pretooluse(payload: dict, script: str, args: list[str]) -> dict:
    if script == "write_guard.py" and is_subagent(payload):
        return {}
    verdict = run_script(script, args, agy_payload(payload, "PreToolUse"))
    hso = {"hookEventName": "PreToolUse"}
    if verdict.get("decision") == "deny":
        hso["permissionDecision"] = "deny"
        hso["permissionDecisionReason"] = claudeify(str(verdict.get("reason") or "denied"))
        return {"hookSpecificOutput": hso}
    rewritten = (verdict.get("overwrite") or {}).get("CommandLine")
    if rewritten and payload.get("tool_name") == "Bash":
        # The rewrite only takes effect on an approved call, which is what the
        # Antigravity gate did too (device_gate's pass verdict is "allow").
        hso["permissionDecision"] = "allow"
        hso["updatedInput"] = {**(payload.get("tool_input") or {}), "command": rewritten}
        return {"hookSpecificOutput": hso}
    return {}


def on_prompt(payload: dict, script: str, args: list[str]) -> dict:
    if script != "intent_gate.py":
        run_script(script, args, agy_payload(payload, "UserPromptSubmit"))
        return {}
    sys.path.insert(0, str(HOOKS_DIR))
    import intent_gate
    prompt = str(payload.get("prompt") or "")
    if (intent_gate.OFF_SWITCH.exists() or intent_gate.MARKER in prompt
            or prompt.lstrip().startswith("/" + intent_gate.SKILL_NAME)
            or not intent_gate.TRIGGER.search(prompt)):
        return {}
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                   "additionalContext": claudeify(intent_gate.DIRECTIVE)}}


def on_stop(payload: dict, event: str, script: str, args: list[str]) -> dict:
    verdict = run_script(script, args, agy_payload(payload, event))
    if verdict.get("decision") == "continue":
        return {"decision": "block", "reason": claudeify(str(verdict.get("reason") or ""))}
    return {}


def on_session_start(payload: dict) -> dict:
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    session = re.sub(r"[^A-Za-z0-9._-]", "_", str(payload.get("session_id") or ""))
    if env_file and session:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f"export AGY_CONVERSATION_ID={session}\n")
    return {}


def main(argv: list[str]) -> int:
    out: dict = {}
    try:
        event = argv[0] if argv else ""
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            payload = {}
        script, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
        if event == "SessionStart":
            out = on_session_start(payload)
        elif event == "PreToolUse":
            out = on_pretooluse(payload, script, args)
        elif event == "UserPromptSubmit":
            out = on_prompt(payload, script, args)
        elif event in ("Stop", "SubagentStop"):
            out = on_stop(payload, event, script, args)
    except Exception as exc:  # fail open: our bug must not block the agent
        print(f"claude_adapter: {type(exc).__name__}: {exc}", file=sys.stderr)
        out = {}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
