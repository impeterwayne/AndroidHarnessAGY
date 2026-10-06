#!/usr/bin/env python3
"""Device gate: one pool of Android devices, many worktrees.

Every worktree that runs the harness shares the devices attached to one machine.
Two agents installing the same `applicationId` overwrite each other, and the
second one's screenshots are of the first one's build -- a failure that looks
exactly like success. `scripts/device_lease.py` is the machine-global arbiter;
this hook makes using it non-optional, for the shell and for mobilerun alike.

PreToolUse on `run_command`:
  * an `adb` command that drives a device takes this worktree's lease and is
    pinned to it: any transport selector the agent wrote (`-s X`, `-t N`, `-d`,
    `-e`) is replaced by `-s <leased serial>`, so an agent cannot reach a device
    it does not hold and never needs to carry a serial;
  * Gradle's `install*`/`connected*`/`uninstall*` tasks are denied -- they pick a
    device themselves -- with the assemble-then-`device_lease.py install` route;
  * `device_lease.py acquire|install` passes, and registers this conversation as
    an owner so the Stop path below releases what it took.

PreToolUse on mobilerun MCP tools:
  * a tool that acts on a device has its `device` argument overwritten with the
    leased serial, whatever the agent passed;
  * the plan-ledger and documentation tools pass untouched;
  * `system_intent` is denied: it takes no `device` argument, so it cannot be
    pinned to the lease.

When every device is leased elsewhere the verdict is `deny`, naming the holders,
plus the blocking command that queues for one: a hook cannot wait minutes, the
agent's own shell call can and stays interruptible. When no device is attached
at all the call passes, so the verifier observes "no device" and reports SKIPPED.

Stop: refcounted by conversationId -- a finishing subagent must not release a
device its dispatcher is still using. The last one out releases the lease.

Fails open on every error: a bug here must never block work.

  hooks/device_gate.py pretooluse       # hook mode: JSON payload on stdin
  hooks/device_gate.py stop             # Stop mode
  hooks/device_gate.py --off|--on|--status
  hooks/device_gate.py --self-test
"""

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = HARNESS_DIR / "state" / "device_gate"
OWNERS_DIR = STATE_DIR / "owners"
OFF_SWITCH = STATE_DIR / "off"
LOG_FILE = STATE_DIR / "log.txt"
LEASE_SCRIPT = HARNESS_DIR / "scripts" / "device_lease.py"

PASS_DECISION = "allow"
QUEUE_WAIT_SEC = 600

SEGMENT_SPLIT = re.compile(r"(\s*(?:&&|\|\||;)\s*)")

# `adb` in command position only -- after env assignments, PowerShell's `&`, or a
# (quoted) path -- so `grep -rn adb docs/` is not mistaken for a device command.
ADB = re.compile(
    r"""^\s*(?:&\s*)?(?:[A-Za-z_]\w*=\S*\s+)*"""
    r"""(?:"[^"]*[/\\]adb(?:\.exe)?"|'[^']*[/\\]adb(?:\.exe)?'|(?:[^\s"']*[/\\])?adb(?:\.exe)?)"""
    r"""(?=\s|$)""",
    re.I,
)
GRADLEW = re.compile(r"(?<![\w.-])(?:\./)?gradlew(?:\.bat)?(?=\s|$)", re.I)
LEASE_CMD = re.compile(r"device_lease\.py[\"']?\s+(?:acquire|install)\b", re.I)

# adb's global options before the subcommand. -s/-t/-d/-e pick the device and
# are replaced by the lease; -H/-P/-L address the adb server and are kept.
ADB_GLOBAL = re.compile(r"\s+(-[stHPL])\s+(\S+)|\s+(-[dea])(?=\s|$)")
ADB_SELECTORS = {"-s", "-t", "-d", "-e"}
# adb subcommands that do not occupy a device (transport/discovery only).
ADB_FREE = re.compile(
    r"^\s*(?:devices|version|help|start-server|kill-server|connect|disconnect|pair|keygen|mdns)\b",
    re.I,
)

GRADLE_DEVICE_TASK = re.compile(
    r"(?<![\w:])(?::[\w:-]+:)?(?:(?:un)?install(?!Dist|ShadowDist)[A-Z]\w*|connected[A-Z]\w*)(?![\w])"
)

# `mcp__mobilerun__tap` in Claude Code; the separator is matched loosely because
# Antigravity's MCP tool naming is unverified.
MOBILERUN_TOOL = re.compile(r"mobilerun(?:__|[_./:])(\w+)$", re.I)
MOBILERUN_UNPINNED = {
    "set_plan", "mark_step", "record_finding", "end_session",
    "get_usage_guide", "web_search", "echo", "list_devices",
}
MOBILERUN_UNPINNABLE = {"system_intent"}


def log(msg):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


_LEASES = None


def leases():
    """scripts/device_lease.py, imported once. Lives beside the hooks in every install."""
    global _LEASES
    if _LEASES is None:
        spec = importlib.util.spec_from_file_location("device_lease", LEASE_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
        _LEASES = module
    return _LEASES


def take_lease(conversation_id):
    """try_acquire for this worktree. Returns None when the lease store is unusable."""
    try:
        dl = leases()
        task = f"agent {conversation_id[:16]}" if conversation_id else "agent session"
        return dl.try_acquire(prefer=dl.preferred(), task=task)
    except Exception as exc:
        log(f"lease: {type(exc).__name__}: {exc}")
        return None


def queue_hint():
    return (
        f"Queue for one -- this blocks until a device frees up, then holds it for this worktree:\n"
        f"  python .agents/scripts/device_lease.py acquire --wait {QUEUE_WAIT_SEC}\n"
        "then retry. If it times out, report the device step SKIPPED (devices busy). Never "
        "pass a serial yourself or reach the device another way."
    )


def busy_reason(result):
    lines = ["Every attached device is leased by another worktree:"]
    for h in result.get("holders", []):
        lines.append(f"  {h['serial']}  held by {h['owner']}  ({h['task'] or 'no task'}, "
                     f"{h['expires_in'] // 60}m left)")
    return "\n".join(lines) + "\n" + queue_hint()


def segments(command):
    """Splits a shell line into command segments, keeping the separators."""
    return SEGMENT_SPLIT.split(command)


def split_adb(segment):
    """(head through `adb`, global options, rest from the subcommand) or None."""
    found = ADB.search(segment)
    if not found:
        return None
    head, rest = segment[: found.end()], segment[found.end():]
    options = []
    while True:
        opt = ADB_GLOBAL.match(rest)
        if not opt:
            break
        options.append((opt.group(1) or opt.group(3), opt.group(0)))
        rest = rest[opt.end():]
    return head, options, rest


def drives_device(segment):
    parts = split_adb(segment)
    return bool(parts) and not ADB_FREE.match(parts[2])


def pin_adb(segment, serial):
    head, options, rest = split_adb(segment)
    kept = "".join(text for flag, text in options if flag not in ADB_SELECTORS)
    return f"{head} -s {serial}{kept}{rest}"


def touches_device(command):
    for seg in segments(command)[::2]:
        if drives_device(seg) or LEASE_CMD.search(seg):
            return True
        if GRADLEW.search(seg) and GRADLE_DEVICE_TASK.search(seg):
            return True
    return False


def policy_denial(command):
    """Returns a reason when the line uses a form that bypasses the lease."""
    for seg in segments(command)[::2]:
        if GRADLEW.search(seg) and GRADLE_DEVICE_TASK.search(seg):
            task = GRADLE_DEVICE_TASK.search(seg).group(0)
            return (
                f"Gradle must not touch a device: `{task}` picks its own target and ignores "
                "the lease, so it installs over whatever another worktree is testing.\n"
                "  1. build:   python .agents/skills/gradle-run/scripts/gradle_run.py run "
                "--workflow <id> --scope broad --question '<q>' -- ./gradlew :app:assembleDebug\n"
                "  2. install: python .agents/scripts/device_lease.py install --launch --json\n"
                "Step 2 leases a device for this worktree, queueing if every one is busy, and "
                "installs the APK step 1 assembled."
            )
    return None


def pin_command(command, serial):
    parts = segments(command)
    for index in range(0, len(parts), 2):
        if drives_device(parts[index]):
            parts[index] = pin_adb(parts[index], serial)
    return "".join(parts)


def register_owner(conversation_id):
    if not conversation_id:
        return
    try:
        OWNERS_DIR.mkdir(parents=True, exist_ok=True)
        (OWNERS_DIR / conversation_id).touch()
    except Exception:
        pass


def gate(conversation_id, on_lease):
    """Common lease step: deny when busy, pass when there is nothing to lease."""
    result = take_lease(conversation_id)
    if result is None or result.get("status") == "no_device":
        return {"decision": PASS_DECISION}
    if result.get("status") == "busy":
        return {"decision": "deny", "reason": busy_reason(result)}
    register_owner(conversation_id)
    return on_lease(result["serial"])


def on_command(payload, args):
    command = args.get("CommandLine") or ""
    if not isinstance(command, str) or not command.strip() or not touches_device(command):
        return {"decision": PASS_DECISION}

    reason = policy_denial(command)
    if reason:
        return {"decision": "deny", "reason": reason}

    conversation_id = payload.get("conversationId") or ""
    if not any(drives_device(seg) for seg in segments(command)[::2]):
        register_owner(conversation_id)  # device_lease.py takes the lease itself
        return {"decision": PASS_DECISION}

    def pinned(serial):
        rewritten = pin_command(command, serial)
        if rewritten == command:
            return {"decision": PASS_DECISION}
        return {"decision": PASS_DECISION, "overwrite": {"CommandLine": rewritten}}

    return gate(conversation_id, pinned)


def on_mobilerun(payload, tool, args):
    if tool in MOBILERUN_UNPINNED:
        return {"decision": PASS_DECISION}
    if tool in MOBILERUN_UNPINNABLE:
        return {
            "decision": "deny",
            "reason": f"mobilerun `{tool}` takes no `device` argument, so it cannot be pinned to "
                      "this worktree's leased device and could act on another worktree's. Drive "
                      "the same flow through the app's UI or a deep link instead.",
        }
    if args.get("device") is not None and not isinstance(args.get("device"), str):
        return {"decision": PASS_DECISION}

    def pinned(serial):
        if args.get("device") == serial:
            return {"decision": PASS_DECISION}
        return {"decision": PASS_DECISION, "overwrite": {"device": serial}}

    return gate(payload.get("conversationId") or "", pinned)


def on_pretooluse(payload):
    call = payload.get("toolCall") or {}
    name = str(call.get("name") or "")
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return {"decision": PASS_DECISION}
    if name == "run_command":
        return on_command(payload, args)
    tool = MOBILERUN_TOOL.search(name)
    if tool:
        return on_mobilerun(payload, tool.group(1).lower(), args)
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

    remaining = list(OWNERS_DIR.glob("*")) if OWNERS_DIR.is_dir() else []
    if remaining:
        log(f"{conv}: released; {len(remaining)} conversation(s) still hold the lease")
        return {"decision": "stop"}

    try:
        released = leases().release()
        log(f"{conv}: last owner -- released {', '.join(released) or 'nothing'}")
    except Exception as exc:
        log(f"{conv}: release failed: {type(exc).__name__}: {exc}")
    return {"decision": "stop"}


HANDLERS = {"pretooluse": on_pretooluse, "stop": on_stop}
SAFE_OUTPUT = {"pretooluse": {"decision": PASS_DECISION}, "stop": {"decision": "stop"}}


# ---------------------------------------------------------------------------
# self-test
# ---------------------------------------------------------------------------

PINNED = [
    ("adb logcat -d -t 400", "adb -s S1 logcat -d -t 400"),
    ("adb shell am force-stop com.example.app", "adb -s S1 shell am force-stop com.example.app"),
    ("adb -s other shell cmd uimode night yes", "adb -s S1 shell cmd uimode night yes"),
    ("adb -d -P 5038 install -r app.apk", "adb -s S1 -P 5038 install -r app.apk"),
    ("adb.exe -e shell input keyevent 4", "adb.exe -s S1 shell input keyevent 4"),
    ("cd app && adb logcat -c", "cd app && adb -s S1 logcat -c"),
    ("adb logcat -c && adb shell ls", "adb -s S1 logcat -c && adb -s S1 shell ls"),
    ('"C:/sdk/platform-tools/adb.exe" shell ls', '"C:/sdk/platform-tools/adb.exe" -s S1 shell ls'),
    ('& "C:/Program Files/sdk/adb.exe" logcat -d', '& "C:/Program Files/sdk/adb.exe" -s S1 logcat -d'),
    ("ANDROID_SERIAL=x adb shell ls", "ANDROID_SERIAL=x adb -s S1 shell ls"),
]

NOT_TOUCHING = [
    "./gradlew :app:assembleDebug",
    "python .agents/skills/gradle-run/scripts/gradle_run.py run --workflow 7 --scope broad -- ./gradlew :app:testDebugUnitTest",
    "git status --porcelain",
    "adb devices",
    "adb devices -l",
    "adb -s foo devices",
    "adb connect 100.97.204.22:5555",
    "grep -rn installDebug docs/",
    "grep -rn adb docs/",
    "echo adb shell ls",
    "python .agents/scripts/device_lease.py list",
    "python .agents/scripts/device_lease.py serial --json",
]

DENIED = [
    "./gradlew :app:installDebug",
    "gradlew.bat :app:connectedDebugAndroidTest",
    "./gradlew uninstallAll",
]


def self_test():
    global take_lease, register_owner
    failures = []

    def check(name, ok):
        if not ok:
            failures.append(name)

    real = take_lease, register_owner
    lease_result = {"status": "ok", "serial": "S1"}
    owners = []
    take_lease = lambda conversation_id: dict(lease_result)
    register_owner = owners.append
    try:
        for cmd, want in PINNED:
            check(f"touches: {cmd}", touches_device(cmd))
            check(f"permitted: {cmd}", policy_denial(cmd) is None)
            check(f"pins: {cmd} -> {pin_command(cmd, 'S1')}", pin_command(cmd, "S1") == want)
        for cmd in NOT_TOUCHING:
            check(f"free: {cmd}", not touches_device(cmd))
        for cmd in DENIED:
            check(f"denied: {cmd}", policy_denial(cmd) is not None)

        def pre(name, args, conv="c1"):
            return on_pretooluse({"toolCall": {"name": name, "args": args}, "conversationId": conv})

        verdict = pre("run_command", {"CommandLine": "adb shell ls"})
        check("rewrites through the handler",
              verdict.get("overwrite", {}).get("CommandLine") == "adb -s S1 shell ls")
        check("registers the owner", owners == ["c1"])
        check("non-device command passes", pre("run_command", {"CommandLine": "ls -la"}) == {"decision": PASS_DECISION})
        check("gradle install denied", pre("run_command", {"CommandLine": "./gradlew :app:installDebug"})["decision"] == "deny")
        owners.clear()
        check("lease script passes untouched",
              pre("run_command", {"CommandLine": "python .agents/scripts/device_lease.py install --launch --json"})
              == {"decision": PASS_DECISION})
        check("lease script registers the owner", owners == ["c1"])

        verdict = pre("mcp__mobilerun__tap_text", {"text": "Login", "device": "other"})
        check("mobilerun device overwritten", verdict.get("overwrite") == {"device": "S1"})
        verdict = pre("mcp__mobilerun__screenshot_path", {})
        check("mobilerun device injected", verdict.get("overwrite") == {"device": "S1"})
        check("mobilerun already pinned passes",
              pre("mcp__mobilerun__ping_device", {"device": "S1"}) == {"decision": PASS_DECISION})
        check("mobilerun ledger passes", pre("mcp__mobilerun__set_plan", {"steps": []}) == {"decision": PASS_DECISION})
        check("mobilerun system_intent denied",
              pre("mcp__mobilerun__system_intent", {"intent": "dial"})["decision"] == "deny")
        check("other MCP tools pass", pre("mcp__figma__get_node", {"id": "1"}) == {"decision": PASS_DECISION})

        lease_result = {"status": "busy", "holders": [
            {"serial": "S1", "owner": "/work/feat-a", "task": "agent x", "expires_in": 600}]}
        verdict = pre("mcp__mobilerun__tap", {"x": 1, "y": 2})
        check("busy denies mobilerun", verdict["decision"] == "deny" and "/work/feat-a" in verdict["reason"])
        verdict = pre("run_command", {"CommandLine": "adb shell ls"})
        check("busy denies adb with the queue command",
              verdict["decision"] == "deny" and "acquire --wait" in verdict["reason"])

        lease_result = {"status": "no_device"}
        check("no device passes adb", pre("run_command", {"CommandLine": "adb shell ls"}) == {"decision": PASS_DECISION})
        check("no device passes mobilerun", pre("mcp__mobilerun__tap", {}) == {"decision": PASS_DECISION})
        check("empty payload passes", on_pretooluse({}) == {"decision": PASS_DECISION})
    finally:
        take_lease, register_owner = real

    total = len(PINNED) * 3 + len(NOT_TOUCHING) + len(DENIED) + 17
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
    try:
        serial = leases().held()
    except Exception as exc:
        serial = None
        print(f"lease store: {type(exc).__name__}: {exc}")
    print(f"lease: {serial}" if serial else "lease: none held by this worktree")
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
