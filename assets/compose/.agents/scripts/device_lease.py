#!/usr/bin/env python3
"""Device leases: one pool of Android devices, many git worktrees.

Two worktrees that install the same applicationId on one device overwrite each
other, and the loser's screenshots show the winner's build -- a failure that reads
as success. This script is the machine-wide arbiter: a worktree holds at most one
device, a device is held by at most one worktree, and every path in the harness
that drives a device (the device-gate hook for `adb` and `mobilerun`, the
verifier's install) resolves its serial here instead of from configuration.

The store is ~/.aha/devices/leases.json (AHA_HOME relocates ~/.aha), guarded by an
exclusive-create lock file, so every worktree on the machine sees the same leases.
A lease is keyed by the worktree's project directory: sessions in one worktree
share its device, and the device-gate hook refcounts them before releasing. A
lease expires after its TTL (topped up on every use), and a lease whose worktree
directory no longer exists is free, so a crashed agent or a deleted worktree
leaks nothing.

  device_lease.py acquire [--wait SEC] [--prefer SERIAL] [--task TEXT] [--json]
  device_lease.py serial  [--json]     the device this worktree holds, if any
  device_lease.py release [--json]
  device_lease.py list    [--json]     attached devices and who holds them
  device_lease.py install [--apk PATH] [--module NAME] [--variant NAME]
                          [--launch] [--wait SEC] [--json]

`install` leases a device, finds the APK Gradle last assembled through its
output-metadata.json (which also names the applicationId), installs it with
`adb -s <leased serial> install -r -d`, and with --launch starts its launcher
activity. It never builds: assemble through the gradle-run wrapper first.

The preferred device, when any free one would do, comes from --prefer, then
AHA_DEVICE, then the untracked `state/device` file `aha --device` writes.

Exit codes: 0 ok, 1 error or no lease held, 2 every device busy, 3 no device.
Stdlib only. Finds `adb` via AHA_ADB, PATH, then ANDROID_HOME / ANDROID_SDK_ROOT.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = HARNESS_DIR.parent
PREFER_FILE = HARNESS_DIR / "state" / "device"

LEASE_TTL_SEC = 1800
POLL_SEC = 3
LOCK_WAIT_SEC = 10
LOCK_STALE_SEC = 30
ADB_TIMEOUT_SEC = 20
INSTALL_TIMEOUT_SEC = 300

EXIT_OK, EXIT_ERROR, EXIT_BUSY, EXIT_NO_DEVICE = 0, 1, 2, 3

SKIP_DIRS = {".git", ".gradle", ".idea", "node_modules", ".agents", ".claude"}


class LeaseError(Exception):
    pass


def store_dir() -> Path:
    return Path(os.environ.get("AHA_HOME") or (Path.home() / ".aha")) / "devices"


def worktree_key(path: Path | str | None = None) -> str:
    return os.path.normcase(os.path.realpath(str(path or PROJECT_DIR)))


def preferred() -> str | None:
    if os.environ.get("AHA_DEVICE"):
        return os.environ["AHA_DEVICE"].strip() or None
    try:
        return PREFER_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# adb
# ---------------------------------------------------------------------------

def adb_path() -> str | None:
    if os.environ.get("AHA_ADB"):
        return os.environ["AHA_ADB"]
    found = shutil.which("adb")
    if found:
        return found
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(var)
        for name in ("adb.exe", "adb"):
            candidate = Path(root) / "platform-tools" / name if root else None
            if candidate and candidate.is_file():
                return str(candidate)
    return None


def adb(args: list[str], timeout: int = ADB_TIMEOUT_SEC) -> subprocess.CompletedProcess:
    exe = adb_path()
    if not exe:
        raise LeaseError("adb not found on PATH, ANDROID_HOME or ANDROID_SDK_ROOT")
    return subprocess.run(
        [exe, *args], capture_output=True, text=True, timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )


def attached_devices() -> list[str]:
    """Serials adb reports as ready; offline and unauthorized devices are not usable."""
    out = adb(["devices"]).stdout
    serials = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------

@contextmanager
def store_lock():
    root = store_dir()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "leases.lock"
    deadline = time.monotonic() + LOCK_WAIT_SEC
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except (FileExistsError, PermissionError):
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE_SEC:
                    lock.unlink()
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise LeaseError(f"{lock} has been held for over {LOCK_WAIT_SEC}s")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def read_leases() -> dict[str, dict]:
    try:
        data = json.loads((store_dir() / "leases.json").read_text(encoding="utf-8"))
        leases = data.get("leases", {})
        return leases if isinstance(leases, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def write_leases(leases: dict[str, dict]) -> None:
    path = store_dir() / "leases.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "leases": leases}, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def live(lease: dict, now: float) -> bool:
    return lease.get("expires_at", 0) > now and Path(str(lease.get("owner", ""))).is_dir()


def live_leases(now: float) -> dict[str, dict]:
    return {serial: lease for serial, lease in read_leases().items() if live(lease, now)}


def describe(serial: str, lease: dict, now: float, owner: str | None = None) -> dict:
    return {
        "serial": serial,
        "owner": lease.get("owner"),
        "task": lease.get("task", ""),
        "expires_in": max(0, int(lease.get("expires_at", 0) - now)),
        "mine": owner is not None and lease.get("owner") == owner,
    }


# ---------------------------------------------------------------------------
# operations
# ---------------------------------------------------------------------------

def try_acquire(owner: str | None = None, prefer: str | None = None, task: str = "",
                ttl: int = LEASE_TTL_SEC, devices: list[str] | None = None) -> dict:
    """Hold-or-claim in one step. Never waits; `acquire` is the waiting form."""
    owner = owner or worktree_key()
    devices = attached_devices() if devices is None else devices
    if not devices:
        return {"status": "no_device"}
    now = time.time()
    with store_lock():
        leases = live_leases(now)
        mine = next((s for s, lease in leases.items() if lease.get("owner") == owner), None)
        if mine and mine not in devices:
            del leases[mine]
            mine = None
        if mine:
            serial = mine
        else:
            free = [s for s in devices if s not in leases]
            if not free:
                write_leases(leases)
                return {"status": "busy",
                        "holders": [describe(s, l, now) for s, l in leases.items() if s in devices]}
            serial = prefer if prefer in free else free[0]
        previous = leases.get(serial, {})
        leases[serial] = {
            "owner": owner,
            "task": task or previous.get("task", ""),
            "acquired_at": previous.get("acquired_at", now),
            "expires_at": now + ttl,
        }
        write_leases(leases)
    return {"status": "ok", "serial": serial, "renewed": bool(mine), "expires_in": ttl}


def acquire(wait: float = 0, owner: str | None = None, prefer: str | None = None,
            task: str = "", ttl: int = LEASE_TTL_SEC) -> dict:
    deadline = time.monotonic() + max(0.0, wait)
    while True:
        result = try_acquire(owner, prefer, task, ttl)
        if result["status"] != "busy" or time.monotonic() >= deadline:
            return result
        time.sleep(min(POLL_SEC, max(0.0, deadline - time.monotonic())))


def held(owner: str | None = None) -> str | None:
    owner = owner or worktree_key()
    for serial, lease in live_leases(time.time()).items():
        if lease.get("owner") == owner:
            return serial
    return None


def release(owner: str | None = None) -> list[str]:
    owner = owner or worktree_key()
    with store_lock():
        now = time.time()
        leases = live_leases(now)
        released = [s for s, lease in leases.items() if lease.get("owner") == owner]
        write_leases({s: l for s, l in leases.items() if s not in released})
    return released


def listing(owner: str | None = None) -> dict:
    owner = owner or worktree_key()
    now = time.time()
    leases = live_leases(now)
    try:
        devices = attached_devices()
    except LeaseError:
        devices = []
    rows = []
    for serial in devices:
        lease = leases.get(serial)
        rows.append(describe(serial, lease, now, owner) if lease
                    else {"serial": serial, "owner": None, "task": "", "expires_in": 0, "mine": False})
    detached = [describe(s, l, now, owner) for s, l in leases.items() if s not in devices]
    return {"devices": rows, "detached_leases": detached, "worktree": owner}


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

def output_metadata(project: Path) -> list[Path]:
    """Every APK output-metadata.json under the project's module build dirs."""
    found = []
    for dirpath, dirnames, _ in os.walk(project):
        if os.path.basename(dirpath) == "build":
            apk_root = Path(dirpath) / "outputs" / "apk"
            if apk_root.is_dir():
                found.extend(apk_root.rglob("output-metadata.json"))
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    return found


def find_apk(project: Path, module: str | None = None, variant: str | None = None) -> dict:
    candidates = []
    for meta_path in output_metadata(project):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = str(meta.get("variantName", ""))
        build_dir = next(p for p in meta_path.parents if p.name == "build")
        module_dir = build_dir.parent
        module_rel = module_dir.relative_to(project).as_posix() if module_dir != project else "."
        if variant is None and name.lower().endswith("androidtest"):
            continue
        if variant is not None and name.lower() != variant.lower():
            continue
        if module is not None and module.strip(":").replace(":", "/") not in (module_rel, module_dir.name):
            continue
        elements = meta.get("elements") or []
        element = next((e for e in elements if not e.get("filters")), elements[0] if elements else None)
        if not element or not element.get("outputFile"):
            continue
        apk = meta_path.parent / element["outputFile"]
        if apk.is_file():
            candidates.append({"path": str(apk), "package_name": meta.get("applicationId"),
                               "variant": name, "module": module_rel,
                               "mtime": apk.stat().st_mtime})
    if not candidates:
        raise LeaseError("no assembled APK found under */build/outputs/apk -- assemble first "
                         "(gradle-run wrapper, e.g. ./gradlew :app:assembleDebug)")
    newest = max(candidates, key=lambda c: c["mtime"])
    newest.pop("mtime")
    return newest


def install(apk: str | None = None, module: str | None = None, variant: str | None = None,
            launch: bool = False, wait: float = 600, task: str = "") -> dict:
    if apk:
        target = {"path": str(Path(apk).resolve()), "package_name": None, "variant": None, "module": None}
        if not Path(target["path"]).is_file():
            raise LeaseError(f"{apk} does not exist")
    else:
        target = find_apk(PROJECT_DIR, module, variant)
    lease = acquire(wait=wait, prefer=preferred(), task=task or "install")
    if lease["status"] != "ok":
        return {**lease, "apk": target}
    serial = lease["serial"]
    proc = adb(["-s", serial, "install", "-r", "-d", target["path"]], timeout=INSTALL_TIMEOUT_SEC)
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0 or "Success" not in output:
        return {"status": "install_failed", "serial": serial, "apk": target,
                "output": output[-2000:]}
    result = {"status": "ok", "serial": serial, "apk": target, "launched": False}
    if launch:
        if not target["package_name"]:
            result["launch_error"] = "package unknown for an explicit --apk; launch it by package id"
        else:
            started = adb(["-s", serial, "shell", "monkey", "-p", target["package_name"],
                           "-c", "android.intent.category.LAUNCHER", "1"])
            launched = started.returncode == 0 and "Events injected" in started.stdout
            result["launched"] = launched
            if not launched:
                result["launch_error"] = (started.stdout + started.stderr).strip()[-1000:]
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def exit_code(result: dict) -> int:
    return {"ok": EXIT_OK, "busy": EXIT_BUSY, "no_device": EXIT_NO_DEVICE}.get(
        result.get("status"), EXIT_ERROR)


def human(command: str, result: dict) -> str:
    status = result.get("status")
    if status == "busy":
        lines = ["every attached device is leased by another worktree:"]
        for h in result.get("holders", []):
            lines.append(f"  {h['serial']}  {h['owner']}  ({h['task'] or 'no task'}, "
                         f"{h['expires_in'] // 60}m left)")
        return "\n".join(lines)
    if status == "no_device":
        return "no Android device attached (adb devices lists none ready)"
    if command == "list":
        lines = [f"worktree {result['worktree']}"]
        for row in result["devices"]:
            holder = ("this worktree" if row["mine"] else row["owner"]) or "free"
            lines.append(f"  {row['serial']:<28} {holder}")
        for row in result["detached_leases"]:
            lines.append(f"  {row['serial']:<28} {row['owner']} (not attached)")
        return "\n".join(lines)
    if command == "install" and status == "ok":
        apk = result["apk"]
        line = f"installed {apk.get('package_name') or apk['path']} on {result['serial']}"
        return line + (" and launched it" if result.get("launched") else "")
    if status == "ok" and result.get("serial"):
        return result["serial"]
    return result.get("error") or result.get("output") or json.dumps(result)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="device_lease.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_acq = sub.add_parser("acquire", help="hold or claim a device for this worktree")
    p_acq.add_argument("--wait", type=float, default=0, help="seconds to queue while every device is busy")
    p_acq.add_argument("--prefer", default=None)
    p_acq.add_argument("--task", default="")
    p_acq.add_argument("--ttl", type=int, default=LEASE_TTL_SEC)
    sub.add_parser("serial", help="print the device this worktree holds")
    sub.add_parser("release", help="release this worktree's device")
    sub.add_parser("list", help="attached devices and their holders")
    p_ins = sub.add_parser("install", help="install the last assembled APK on the leased device")
    p_ins.add_argument("--apk", default=None)
    p_ins.add_argument("--module", default=None)
    p_ins.add_argument("--variant", default=None)
    p_ins.add_argument("--launch", action="store_true")
    p_ins.add_argument("--wait", type=float, default=600)
    p_ins.add_argument("--task", default="")
    for p in sub.choices.values():
        p.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    try:
        if args.command == "acquire":
            result = acquire(args.wait, prefer=args.prefer or preferred(), task=args.task, ttl=args.ttl)
        elif args.command == "serial":
            serial = held()
            result = {"status": "ok", "serial": serial} if serial else {"status": "none", "error": "no lease held by this worktree"}
        elif args.command == "release":
            result = {"status": "ok", "released": release()}
        elif args.command == "list":
            result = {"status": "ok", **listing()}
        else:
            result = install(args.apk, args.module, args.variant, args.launch, args.wait, args.task)
    except (LeaseError, subprocess.TimeoutExpired, OSError) as exc:
        result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        text = human(args.command, result)
        if args.command == "release" and result.get("status") == "ok":
            text = f"released {', '.join(result['released'])}" if result["released"] else "no lease held"
        print(text, file=sys.stdout if result.get("status") == "ok" else sys.stderr)
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
