#!/usr/bin/env python3
"""Lifecycle management for the scrcpy-cli daemon.

The agent never runs `daemon start` / `daemon stop` itself -- this handler owns the
daemon, so the scrcpy skill can just issue actions. Started on the first LLM call of
a conversation and stopped when the last conversation using it finishes.

`PreInvocation` fires on every LLM call (~50 per session, measured), so the handler
early-exits on a marker file: the start path runs once per conversation, and every
later call is a single marker check with no subprocess.

Why PreInvocation / Stop and never PreToolUse: `PreToolUse` must return a required
`decision` field for *every* matched call, which would mean issuing a verdict on
every single `run_command` -- either downgrading an auto-exec policy to prompting
("ask") or silently auto-approving all shell commands ("allow"). `PreInvocation`
and `Stop` cannot affect approvals at all, so device management stays out of the
permission path entirely.

Cleanup is refcounted by conversationId: subagents get their own `Stop` event, so a
child finishing must not kill a daemon its parent is still using. The daemon is only
stopped if this handler was the one that started it -- a daemon the user launched by
hand is left alone.

Usage:
  hooks/scrcpy_daemon.py preinvocation   # ensure the daemon is up for this conversation
  hooks/scrcpy_daemon.py stop            # release this conversation, stop if last
  hooks/scrcpy_daemon.py --self-test     # signal-detection assertions
  hooks/scrcpy_daemon.py --status        # show handler state and daemon state
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Machine-global: one scrcpy daemon serves every worktree, so a per-worktree owner
# refcount would let one session's Stop kill the daemon another session is driving.
STATE_DIR = Path(os.environ.get("ANDRUN_HOME") or (Path.home() / ".andrun")) / "scrcpy"
OWNERS_DIR = STATE_DIR / "owners"
STARTED_FLAG = STATE_DIR / "started-by-hook"
NO_DEVICE_UNTIL = STATE_DIR / "no-device-until"
LOG = STATE_DIR / "events.log"

TRANSCRIPT_TAIL_BYTES = 65536
CLI = "scrcpy-cli"

# True  -- bring the daemon up for every conversation (current behaviour).
# False -- only bring it up once the transcript shows device work, per SIGNALS below.
ALWAYS_START = True

# How long to trust a "no device attached" result before checking again. Without this,
# a session with no device would re-probe on all ~50 invocations.
NO_DEVICE_TTL_SECONDS = 60

# Signals that this conversation is doing real device work. Used only when
# ALWAYS_START is False. Deliberately specific: vague tokens like "test" would start a
# daemon on every unit-test run.
SIGNALS = re.compile(
    r"""
      scrcpy-cli\s+(?:tap|swipe|write|key|scroll|screenshot|ui-dump|clipboard-|app-|device-|mirror|view|gui)
    | \bui-dump\b
    | \buiautomator\b
    | \bconnectedAndroidTest\b
    | \bconnectedCheck\b
    | \bam\s+instrument\b
    | \bskills?/scrcpy\b
    # An activated skill block. Observed transcripts use a bare <SKILL> tag with the
    # name in the body; [^<] also covers an attribute form without escaping the tag.
    | <SKILL[^<]{0,4000}?scrcpy
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)


def log(msg):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(msg.rstrip() + "\n")
    except Exception:
        pass


def run(args, timeout=15):
    """Run scrcpy-cli and return (ok, stdout). Exit codes are unreliable -- it
    returns 0 even for 'No Android devices connected' -- so callers parse text."""
    try:
        p = subprocess.run(
            [CLI] + args, capture_output=True, text=True, timeout=timeout
        )
        return True, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return False, f"{CLI} not on PATH"
    except subprocess.TimeoutExpired:
        return False, f"{CLI} {' '.join(args)} timed out"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def daemon_running():
    ok, out = run(["daemon", "status"], timeout=10)
    if not ok:
        return None
    return "running" in out.lower() and "stopped" not in out.lower()


def device_connected():
    ok, out = run(["device-list"], timeout=10)
    if not ok:
        return None
    return "no android devices" not in out.lower()


def spawn_daemon_start():
    """Start the daemon without blocking the agent loop.

    Detached: the hook process exits immediately after this, and actions have a
    stateless fallback path, so nothing needs to wait for readiness.
    """
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    subprocess.Popen(
        [CLI, "daemon", "start"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


def transcript_tail(path):
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        with p.open("rb") as fh:
            size = p.stat().st_size
            if size > TRANSCRIPT_TAIL_BYTES:
                fh.seek(-TRANSCRIPT_TAIL_BYTES, os.SEEK_END)
            return fh.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def needs_device(text):
    return bool(SIGNALS.search(text))


def no_device_cache_active():
    try:
        return time.time() < float(NO_DEVICE_UNTIL.read_text(encoding="utf-8").strip())
    except Exception:
        return False


def on_preinvocation(payload):
    conv = payload.get("conversationId") or "unknown"
    marker = OWNERS_DIR / conv

    # Fast path: the daemon is already handled for this conversation. No subprocess,
    # no transcript read -- this is the branch that runs ~50 times per session.
    if marker.exists():
        return

    if not ALWAYS_START and not needs_device(transcript_tail(payload.get("transcriptPath"))):
        return

    if no_device_cache_active():
        return

    connected = device_connected()
    if connected is False:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        NO_DEVICE_UNTIL.write_text(str(time.time() + NO_DEVICE_TTL_SECONDS), encoding="utf-8")
        log(f"{conv}: no device attached -- not starting (recheck in {NO_DEVICE_TTL_SECONDS}s)")
        return
    if connected is None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        NO_DEVICE_UNTIL.write_text(str(time.time() + NO_DEVICE_TTL_SECONDS), encoding="utf-8")
        log(f"{conv}: {CLI} unavailable -- not starting (recheck in {NO_DEVICE_TTL_SECONDS}s)")
        return

    running = daemon_running()
    OWNERS_DIR.mkdir(parents=True, exist_ok=True)
    marker.write_text("owner\n", encoding="utf-8")

    if running:
        # Someone else's daemon (or a leftover). Use it, never claim it for cleanup.
        log(f"{conv}: daemon already running -- attached without claiming ownership")
        return

    spawn_daemon_start()
    STARTED_FLAG.write_text("1\n", encoding="utf-8")
    log(f"{conv}: daemon start spawned")


def on_stop(payload):
    conv = payload.get("conversationId") or "unknown"
    marker = OWNERS_DIR / conv
    if marker.exists():
        try:
            marker.unlink()
        except Exception:
            pass

    remaining = [p for p in OWNERS_DIR.glob("*")] if OWNERS_DIR.is_dir() else []
    if remaining:
        log(f"{conv}: released; {len(remaining)} conversation(s) still using the daemon")
        return

    if not STARTED_FLAG.exists():
        log(f"{conv}: released; daemon was not started by this hook -- leaving it alone")
        return

    ok, out = run(["daemon", "stop"], timeout=15)
    try:
        STARTED_FLAG.unlink()
    except Exception:
        pass
    log(f"{conv}: last owner released -- daemon stop ({'ok' if ok else out.strip()})")


HANDLERS = {"preinvocation": on_preinvocation, "stop": on_stop}
SAFE_OUTPUT = {"stop": {"decision": "stop"}}

POSITIVE_FIXTURES = [
    'run "scrcpy-cli tap 540 960" to press the button',
    "scrcpy-cli ui-dump layout.xml",
    "let's capture the device with scrcpy-cli screenshot verify.png",
    "./gradlew :app:connectedAndroidTest",
    "adb shell am instrument -w com.genesys.test/androidx.test.runner.AndroidJUnitRunner",
    "<SKILL>\n# scrcpy\nAndroid Device Control via CLI\n</SKILL>",  # observed bare-tag form
    '<SKILL name="scrcpy">Android Device Control via CLI</SKILL>',  # defensive attribute form
    "run the uiautomator dump",
]
NEGATIVE_FIXTURES = [
    "./gradlew :app:testDebugUnitTest",
    "write the unit tests for the ViewModel",
    "please run the test suite and report failures",
    "implement HomeScreen.kt with AppTheme tokens",
    "view_file on .agents/skills/testing-setup/SKILL.md",
    "the screenshot test baseline needs updating",  # Paparazzi, not device work
]


def self_test():
    failures = 0
    for text in POSITIVE_FIXTURES:
        if not needs_device(text):
            failures += 1
            print(f"  FAIL  should trigger: {text[:70]}")
        else:
            print(f"  PASS  triggers: {text[:70]}")
    for text in NEGATIVE_FIXTURES:
        if needs_device(text):
            failures += 1
            print(f"  FAIL  should NOT trigger: {text[:70]}")
        else:
            print(f"  PASS  ignores: {text[:70]}")
    total = len(POSITIVE_FIXTURES) + len(NEGATIVE_FIXTURES)
    print(f"\n{total - failures}/{total} signal fixtures passed")
    return 1 if failures else 0


def show_status():
    owners = sorted(p.name for p in OWNERS_DIR.glob("*")) if OWNERS_DIR.is_dir() else []
    print(f"owners ({len(owners)}): {owners or 'none'}")
    print(f"started-by-hook flag: {STARTED_FLAG.exists()}")
    print(f"daemon running: {daemon_running()}")
    print(f"device connected: {device_connected()}")
    if LOG.exists():
        tail = LOG.read_text(encoding="utf-8").splitlines()[-8:]
        print("recent events:")
        for line in tail:
            print(f"  {line}")
    return 0


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    if "--status" in sys.argv:
        sys.exit(show_status())

    event = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        handler = HANDLERS.get(event)
        if handler:
            handler(payload if isinstance(payload, dict) else {})
    except Exception as exc:
        print(f"scrcpy_daemon: {type(exc).__name__}: {exc}", file=sys.stderr)

    print(json.dumps(SAFE_OUTPUT.get(event, {})))


if __name__ == "__main__":
    main()
