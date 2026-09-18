#!/usr/bin/env python3
"""Device gate: one Android device, many worktrees.

Every worktree that runs the harness shares one pool of attached devices. Two
agents installing the same `applicationId` overwrite each other, and the second
one's screenshots are of the first one's build -- a failure that looks exactly
like success. `andrun`'s lease store (~/.andrun/device_queue.json) is the
machine-global arbiter; this hook makes using it non-optional.

PreToolUse on `run_command`:
  * a command that drives a device (`scrcpy-cli`, `adb`) is rewritten to run
    under `andrun with`, which holds this worktree's lease, QUEUES for a device
    when every one is busy, points the command at the leased serial and exports
    ANDROID_SERIAL. The wait therefore happens inside the agent's own tool call,
    which has minutes of budget -- not in this hook, which has seconds, and not
    as a suggestion the agent is free to decline;
  * `andrun`'s own device commands pass through untouched: they resolve this
    worktree's lease and queue for a device by themselves;
  * the forms that pick a device themselves and ignore the lease entirely are
    denied with their replacement: `adb install`, Gradle's
    `install*`/`connected*`/`uninstall*` tasks, `andrun install`/`run` without
    `--no-build` (which would also run Gradle outside the gradle-run wrapper),
    and `scrcpy-cli daemon start|stop` (the scrcpy-daemon hook owns those).

No subprocess runs on the PreToolUse path: classification is pure regex, so the
cost is one Python start per `run_command`.

Stop: refcounted by conversationId, like scrcpy_daemon -- a finishing subagent
must not release a device its dispatcher is still using. The last one out
releases the lease.

Fails open on every error: a bug here must never block work.

  hooks/device_gate.py                  # hook mode: JSON payload on stdin
  hooks/device_gate.py stop             # Stop mode
  hooks/device_gate.py --off|--on|--status
  hooks/device_gate.py --self-test
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent.parent / "state" / "device_gate"
OWNERS_DIR = STATE_DIR / "owners"
OFF_SWITCH = STATE_DIR / "off"
LOG_FILE = STATE_DIR / "log.txt"

PASS_DECISION = "allow"

# How long a blocked device command waits for a free device, inside the agent's
# own tool call. Long enough to outlast another worktree's verification.
QUEUE_WAIT_SEC = 600
LEASE_TTL_SEC = 1800
ANDRUN_TIMEOUT_SEC = 20

SEGMENT_SPLIT = re.compile(r"(\s*(?:&&|\|\||;)\s*)")

ADB = re.compile(r"(?<![\w.-])adb(?:\.exe)?(?=\s|$)", re.I)
SCRCPY = re.compile(r"(?<![\w.-])scrcpy-cli(?:\.exe|\.cmd)?(?=\s|$)", re.I)
ANDRUN = re.compile(r"(?<![\w.-])andrun(?:\.exe|\.bat|\.cmd)?(?=\s|$)", re.I)
GRADLEW = re.compile(r"(?<![\w.-])(?:\./)?gradlew(?:\.bat)?(?=\s|$)", re.I)

# adb subcommands that do not occupy a device (transport/discovery only).
ADB_FREE = re.compile(
    r"^\s*(?:-[a-z]\s+\S+\s+)*(?:devices|version|help|start-server|kill-server|connect|disconnect|pair|keygen)\b",
    re.I,
)
# scrcpy-cli actions that only report; leasing for these would lock a device for
# a status check.
SCRCPY_FREE = re.compile(r"(?<!\S)(?:device-list|version|update|daemon\s+status)(?!\S)", re.I)
# andrun subcommands that read the pool rather than drive a device.
ANDRUN_FREE = re.compile(
    r"(?<!\S)(?:devices|detect|serial|queue|scan-ports|pair|connect|disconnect|--version|-V|--help|tui)(?!\S)",
    re.I,
)

GRADLE_DEVICE_TASK = re.compile(
    r"(?<![\w:])(?::[\w:-]+:)?(?:(?:un)?install(?!Dist|ShadowDist)[A-Z]\w*|connected[A-Z]\w*)(?![\w])"
)

ALREADY_WRAPPED = re.compile(r"^andrun(?:\.exe|\.bat|\.cmd)?\s+with(?:\s|$)", re.I)

DENIALS = (
    (
        re.compile(r"(?<![\w.-])adb(?:\.exe)?\s(?:[^&|;]*\s)?install\b", re.I),
        "`adb install` bypasses the device lease and ignores which worktree owns the device.\n"
        "  andrun install <apk> --no-build --launch --json\n"
        "andrun resolves this worktree's lease itself, queueing for a device if one is busy.",
    ),
    (
        re.compile(r"(?<![\w.-])scrcpy-cli(?:\.exe|\.cmd)?\s+daemon\s+(?:start|stop)\b", re.I),
        "The scrcpy daemon is owned by the scrcpy-daemon hook, which refcounts it across "
        "conversations. Issue actions directly; never start or stop the daemon yourself.",
    ),
)


def log(msg):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


def andrun_cmd():
    exe = shutil.which("andrun")
    return [exe] if exe else [sys.executable, "-m", "andrun"]


def andrun_json(args, cwd, timeout=ANDRUN_TIMEOUT_SEC):
    """Runs andrun and returns (parsed_json_or_None, returncode). Stop path only."""
    try:
        proc = subprocess.run(
            andrun_cmd() + args + ["--json"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except Exception as exc:
        log(f"andrun {' '.join(args)}: {type(exc).__name__}: {exc}")
        return None, -1
    try:
        return json.loads(proc.stdout.strip() or "{}"), proc.returncode
    except Exception:
        log(f"andrun {' '.join(args)}: unparseable output: {proc.stdout[:200]!r}")
        return None, proc.returncode


def segments(command):
    """Splits a shell line into command segments, keeping the separators."""
    return SEGMENT_SPLIT.split(command)


def drives_device(segment):
    """True when this segment drives a device through a tool that has no lease of its own."""
    if SCRCPY.search(segment) and not SCRCPY_FREE.search(segment):
        return True
    if ADB.search(segment) and not ADB_FREE.search(ADB.split(segment, 1)[-1]):
        return True
    return False


def occupies_device(segment):
    """True when this segment needs the lease held for the whole turn.

    `andrun install` takes a command-scoped lock it drops on exit, so between the
    install and the screenshot the device is free and another worktree can take
    it -- the screenshot would then be of someone else's build. Wrapping andrun
    in `andrun with` upgrades that to a session lease the Stop hook releases.
    """
    if drives_device(segment):
        return True
    return bool(ANDRUN.search(segment)) and not ANDRUN_FREE.search(ANDRUN.split(segment, 1)[-1])


def touches_device(command):
    """True when any segment occupies a device, including via andrun or Gradle."""
    for seg in segments(command)[::2]:
        if drives_device(seg):
            return True
        if GRADLEW.search(seg) and GRADLE_DEVICE_TASK.search(seg):
            return True
        if ANDRUN.search(seg) and not ANDRUN_FREE.search(ANDRUN.split(seg, 1)[-1]):
            return True
    return False


def policy_denial(command):
    """Returns a reason when the line uses a form that bypasses the lease."""
    for pattern, reason in DENIALS:
        if pattern.search(command):
            return reason

    for seg in segments(command)[::2]:
        if GRADLEW.search(seg) and GRADLE_DEVICE_TASK.search(seg):
            task = GRADLE_DEVICE_TASK.search(seg).group(0)
            return (
                f"Gradle must not touch a device: `{task}` picks its own target and ignores "
                "the lease, so it installs over whatever another worktree is testing.\n"
                "  1. build:   python .agents/skills/gradle-run/scripts/gradle_run.py run "
                "--workflow <id> --scope broad --question '<q>' -- ./gradlew :app:assembleDebug\n"
                "  2. install: andrun install --no-build --launch --json\n"
                "Step 2 resolves this worktree's lease and the variant APK itself, and queues "
                "for a device if every one is busy."
            )
        if ANDRUN.search(seg):
            rest = ANDRUN.split(seg, 1)[-1]
            if re.search(r"(?<!\S)(?:install|run)(?!\S)", rest, re.I) and not re.search(
                r"(?<!\S)(?:--no-build|-b\s+false)(?!\S)", rest, re.I
            ):
                return (
                    "`andrun install`/`andrun run` force-rebuild by default, which runs Gradle "
                    "outside the gradle-run wrapper and floods the context with an unbounded log.\n"
                    "  andrun install --no-build --launch --json\n"
                    "Build with the wrapper first; andrun then installs the variant APK it finds."
                )
    return None


def wrap_device_segments(command, agent_id=""):
    """Route every device-driving segment through `andrun with`.

    `andrun with` holds the worktree's lease, queues when every device is busy,
    targets the leased serial and exports ANDROID_SERIAL. Wrapping per segment
    rather than per line keeps the shell's own `&&`/`;` structure intact.
    """
    parts = segments(command)
    changed = False
    prefix = f"andrun with --wait {QUEUE_WAIT_SEC} --ttl {LEASE_TTL_SEC}"
    if agent_id:
        prefix += f' --agent-id {agent_id} --task "Harness device session"'
    for index in range(0, len(parts), 2):
        segment = parts[index]
        stripped = segment.strip()
        if not occupies_device(segment) or ALREADY_WRAPPED.match(stripped):
            continue
        lead = segment[: len(segment) - len(segment.lstrip())]
        parts[index] = f"{lead}{prefix} -- {stripped}"
        changed = True
    return ("".join(parts), changed)


def register_owner(conversation_id):
    if not conversation_id:
        return
    try:
        OWNERS_DIR.mkdir(parents=True, exist_ok=True)
        (OWNERS_DIR / conversation_id).touch()
    except Exception:
        pass


def on_pretooluse(payload):
    call = payload.get("toolCall") or {}
    args = call.get("args") or {}
    command = args.get("CommandLine") or ""
    if not isinstance(command, str) or not command.strip():
        return {"decision": PASS_DECISION}

    if not touches_device(command):
        return {"decision": PASS_DECISION}

    reason = policy_denial(command)
    if reason:
        return {"decision": "deny", "reason": reason}

    conversation_id = payload.get("conversationId") or ""
    register_owner(conversation_id)

    rewritten, changed = wrap_device_segments(command, conversation_id[:16])
    if changed:
        return {"decision": PASS_DECISION, "overwrite": {"CommandLine": rewritten}}
    return {"decision": PASS_DECISION}


def on_stop(payload):
    conv = payload.get("conversationId") or "unknown"
    marker = OWNERS_DIR / conv
    if not marker.exists():
        return {"decision": "stop"}

    try:
        marker.unlink()
    except Exception:
        pass

    remaining = [p for p in OWNERS_DIR.glob("*")] if OWNERS_DIR.is_dir() else []
    if remaining:
        log(f"{conv}: released; {len(remaining)} conversation(s) still hold the lease")
        return {"decision": "stop"}

    workspaces = payload.get("workspacePaths") or []
    cwd = workspaces[0] if workspaces else str(STATE_DIR.parent.parent.parent)
    result, _ = andrun_json(["queue", "release"], cwd=cwd)
    log(f"{conv}: last owner -- release {(result or {}).get('status', 'failed')}")
    return {"decision": "stop"}


HANDLERS = {"pretooluse": on_pretooluse, "stop": on_stop}
SAFE_OUTPUT = {"pretooluse": {"decision": PASS_DECISION}, "stop": {"decision": "stop"}}


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

WRAPPED = [
    "scrcpy-cli screenshot .agents/state/verify/01.png",
    "scrcpy-cli ui-dump layout.xml",
    "scrcpy-cli tap 540 960",
    "adb logcat -d -t 400",
    "adb shell am force-stop com.example.app",
]

PASSED_THROUGH = [
    "andrun install --no-build --launch --json",
    "andrun install app.apk --no-build --json",
]  # wrapped too: their own lock is command-scoped

NOT_TOUCHING = [
    "./gradlew :app:assembleDebug",
    "python .agents/skills/gradle-run/scripts/gradle_run.py run --workflow 7 --scope broad -- ./gradlew :app:testDebugUnitTest",
    "git status --porcelain",
    "andrun devices --json",
    "andrun queue list --json",
    "andrun serial",
    "scrcpy-cli device-list",
    "adb devices",
    "adb connect 100.97.204.22:5555",
    "grep -rn installDebug docs/",
]

DENIED = [
    "adb install -r app-debug.apk",
    "adb -s foo install app/build/outputs/apk/debug/app-debug.apk",
    "./gradlew :app:installDebug",
    "gradlew.bat :app:connectedDebugAndroidTest",
    "andrun install",
    "andrun run --launch",
    "scrcpy-cli daemon start",
]


def self_test():
    failures = []

    def check(name, ok):
        if not ok:
            failures.append(name)

    for cmd in WRAPPED + PASSED_THROUGH:
        check(f"touches: {cmd}", touches_device(cmd))
    for cmd in NOT_TOUCHING:
        check(f"free: {cmd}", not touches_device(cmd))
    for cmd in DENIED:
        check(f"denied: {cmd}", policy_denial(cmd) is not None)
    for cmd in WRAPPED + PASSED_THROUGH:
        check(f"permitted: {cmd}", policy_denial(cmd) is None)

    out, changed = wrap_device_segments("scrcpy-cli screenshot a.png")
    check(
        "wraps scrcpy-cli",
        changed
        and out == f"andrun with --wait {QUEUE_WAIT_SEC} --ttl {LEASE_TTL_SEC} -- scrcpy-cli screenshot a.png",
    )
    out, changed = wrap_device_segments("adb logcat -d")
    check("wraps adb", changed and out.endswith("-- adb logcat -d"))
    out, changed = wrap_device_segments("andrun install --no-build --json")
    check("wraps andrun install into a session lease", changed and out.endswith("-- andrun install --no-build --json"))
    out, changed = wrap_device_segments("adb devices")
    check("leaves a device listing alone", not changed)
    out, changed = wrap_device_segments("andrun queue list --json")
    check("leaves a queue listing alone", not changed)
    out, changed = wrap_device_segments("cd app && scrcpy-cli tap 1 2")
    check("keeps shell structure", changed and out.startswith("cd app && andrun with"))
    out, changed = wrap_device_segments("scrcpy-cli ui-dump a.xml && scrcpy-cli screenshot b.png")
    check("wraps every segment", out.count("andrun with") == 2)
    out, changed = wrap_device_segments(f"andrun with --wait {QUEUE_WAIT_SEC} -- scrcpy-cli tap 1 2")
    check("does not double-wrap", not changed)
    out, changed = wrap_device_segments("scrcpy-cli tap 1 2", "conv-123")
    check("records the agent id", "--agent-id conv-123" in out)

    check("empty payload passes", on_pretooluse({}).get("decision") == PASS_DECISION)
    check(
        "non-device command passes",
        on_pretooluse({"toolCall": {"name": "run_command", "args": {"CommandLine": "ls -la"}}}).get("decision")
        == PASS_DECISION,
    )
    verdict = on_pretooluse(
        {
            "toolCall": {"name": "run_command", "args": {"CommandLine": "scrcpy-cli screenshot x.png"}},
            "conversationId": "abc",
        }
    )
    check("rewrites through the handler", "andrun with" in verdict.get("overwrite", {}).get("CommandLine", ""))
    check(
        "gradle install denied",
        on_pretooluse(
            {"toolCall": {"name": "run_command", "args": {"CommandLine": "./gradlew :app:installDebug"}}}
        ).get("decision")
        == "deny",
    )

    total = len(WRAPPED + PASSED_THROUGH) * 2 + len(NOT_TOUCHING) + len(DENIED) + 14
    for name in failures:
        print(f"FAIL {name}")
    print(f"{total - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


def show_status():
    owners = sorted(p.name for p in OWNERS_DIR.glob("*")) if OWNERS_DIR.is_dir() else []
    print(f"device_gate: {'OFF' if OFF_SWITCH.exists() else 'ON'}")
    print(f"owners: {len(owners)}")
    for o in owners:
        print(f"  {o}")
    result, _ = andrun_json(["serial"], cwd=str(STATE_DIR.parent.parent.parent), timeout=15)
    if result and result.get("status") == "ok":
        print(f"lease: {result['lease_id']} on {result.get('device_name') or result['serial']}")
    else:
        print("lease: none held by this worktree")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    if "--status" in argv:
        return show_status()
    if "--off" in argv:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        OFF_SWITCH.touch()
        print("device_gate: OFF")
        return 0
    if "--on" in argv:
        OFF_SWITCH.unlink(missing_ok=True)
        print("device_gate: ON")
        return 0

    event = (argv[0] if argv else "pretooluse").lower()
    verdict = SAFE_OUTPUT.get(event, SAFE_OUTPUT["pretooluse"])
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if OFF_SWITCH.exists():
            print(json.dumps(verdict))
            return 0
        handler = HANDLERS.get(event, on_pretooluse)
        verdict = handler(payload)
    except Exception as exc:  # fail open: our bug must not block the agent
        print(f"device_gate: {type(exc).__name__}: {exc}", file=sys.stderr)
    print(json.dumps(verdict))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
