import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AHA_SCRIPT = ROOT / "aha.py"
TRACKS = ("compose", "xml")


def load_lease_module():
    path = ROOT / "assets" / "compose" / ".agents" / "scripts" / "device_lease.py"
    spec = importlib.util.spec_from_file_location("device_lease_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_adb(directory: Path, devices: list[str]) -> tuple[Path, Path]:
    """An adb stand-in that lists `devices`, logs every other call, and succeeds."""
    log = directory / "adb_calls.jsonl"
    script = directory / "fake_adb.py"
    script.write_text(
        "import json, sys\n"
        f"DEVICES = {devices!r}\n"
        f"LOG = {str(log)!r}\n"
        "args = sys.argv[1:]\n"
        "if args == ['devices']:\n"
        "    print('List of devices attached')\n"
        "    for d in DEVICES:\n"
        "        print(d + '\\tdevice')\n"
        "    sys.exit(0)\n"
        "with open(LOG, 'a') as fh:\n"
        "    fh.write(json.dumps(args) + '\\n')\n"
        "if 'install' in args:\n"
        "    print('Performing Streamed Install')\n"
        "    print('Success')\n"
        "elif 'monkey' in args:\n"
        "    print('Events injected: 1')\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        wrapper = directory / "adb.cmd"
        wrapper.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        wrapper = directory / "adb"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
        wrapper.chmod(0o755)
    return wrapper, log


def write_apk(module_dir: Path, variant: str, application_id: str, mtime: float | None = None) -> Path:
    out = module_dir / "build" / "outputs" / "apk" / variant
    out.mkdir(parents=True, exist_ok=True)
    apk = out / f"{module_dir.name}-{variant}.apk"
    apk.write_bytes(b"PK")
    (out / "output-metadata.json").write_text(json.dumps({
        "version": 3, "applicationId": application_id, "variantName": variant,
        "elements": [{"type": "SINGLE", "filters": [], "outputFile": apk.name}],
    }), encoding="utf-8")
    if mtime is not None:
        os.utime(apk, (mtime, mtime))
    return apk


class LeaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.saved_env = {k: os.environ.get(k) for k in ("AHA_HOME", "AHA_ADB", "AHA_DEVICE")}
        os.environ["AHA_HOME"] = str(self.root / "home")
        os.environ.pop("AHA_ADB", None)
        os.environ.pop("AHA_DEVICE", None)
        self.dl = load_lease_module()
        self.dl.POLL_SEC = 0.05
        self.devices = ["S1", "S2"]
        self.dl.attached_devices = lambda: list(self.devices)
        self.a = self.worktree("a")
        self.b = self.worktree("b")
        self.c = self.worktree("c")

    def tearDown(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()

    def worktree(self, name):
        path = self.root / name
        path.mkdir()
        return self.dl.worktree_key(path)


class TestDeviceLease(LeaseTestCase):
    def test_claim_renew_and_exclusive_ownership(self):
        first = self.dl.try_acquire(self.a)
        self.assertEqual((first["status"], first["serial"], first["renewed"]), ("ok", "S1", False))
        again = self.dl.try_acquire(self.a)
        self.assertEqual((again["serial"], again["renewed"]), ("S1", True))
        self.assertEqual(self.dl.try_acquire(self.b)["serial"], "S2")
        busy = self.dl.try_acquire(self.c, task="verify")
        self.assertEqual(busy["status"], "busy")
        self.assertEqual({h["owner"] for h in busy["holders"]}, {self.a, self.b})
        self.assertEqual(self.dl.held(self.a), "S1")
        self.assertIsNone(self.dl.held(self.c))

    def test_release_frees_the_device_for_another_worktree(self):
        self.devices = ["S1"]
        self.dl.try_acquire(self.a)
        self.assertEqual(self.dl.try_acquire(self.b)["status"], "busy")
        self.assertEqual(self.dl.release(self.a), ["S1"])
        self.assertEqual(self.dl.try_acquire(self.b)["serial"], "S1")

    def test_preferred_device_when_free(self):
        self.assertEqual(self.dl.try_acquire(self.a, prefer="S2")["serial"], "S2")
        self.assertEqual(self.dl.try_acquire(self.b, prefer="S2")["serial"], "S1")

    def test_expired_lease_is_free(self):
        self.devices = ["S1"]
        self.dl.try_acquire(self.a, ttl=-1)
        self.assertEqual(self.dl.try_acquire(self.b)["serial"], "S1")

    def test_lease_of_a_deleted_worktree_is_free(self):
        self.devices = ["S1"]
        self.dl.try_acquire(self.a)
        shutil.rmtree(self.a)
        self.assertEqual(self.dl.try_acquire(self.b)["serial"], "S1")

    def test_detached_device_is_replaced(self):
        self.dl.try_acquire(self.a)
        self.devices = ["S2"]
        self.assertEqual(self.dl.try_acquire(self.a)["serial"], "S2")

    def test_no_device(self):
        self.devices = []
        self.assertEqual(self.dl.try_acquire(self.a)["status"], "no_device")

    def test_acquire_queues_until_released(self):
        self.devices = ["S1"]
        self.dl.try_acquire(self.a)
        timer = threading.Timer(0.3, self.dl.release, args=(self.a,))
        timer.start()
        start = time.monotonic()
        result = self.dl.acquire(wait=5, owner=self.b)
        timer.join()
        self.assertEqual(result["serial"], "S1")
        self.assertLess(time.monotonic() - start, 4)

    def test_acquire_gives_up_after_wait(self):
        self.devices = ["S1"]
        self.dl.try_acquire(self.a)
        self.assertEqual(self.dl.acquire(wait=0.2, owner=self.b)["status"], "busy")

    def test_stale_lock_file_is_broken(self):
        store = Path(os.environ["AHA_HOME"]) / "devices"
        store.mkdir(parents=True)
        lock = store / "leases.lock"
        lock.write_text("999999")
        old = time.time() - 120
        os.utime(lock, (old, old))
        self.assertEqual(self.dl.try_acquire(self.a)["status"], "ok")
        self.assertFalse(lock.exists())


class TestFindApkAndInstall(LeaseTestCase):
    def setUp(self):
        super().setUp()
        self.project = self.root / "a"
        self.dl.PROJECT_DIR = self.project

    def test_newest_app_apk_wins_and_android_test_is_skipped(self):
        now = time.time()
        write_apk(self.project / "app", "debug", "com.example.app", now - 100)
        write_apk(self.project / "app", "release", "com.example.app", now)
        write_apk(self.project / "app", "debugAndroidTest", "com.example.app.test", now + 50)
        found = self.dl.find_apk(self.project)
        self.assertEqual((found["variant"], found["package_name"], found["module"]),
                         ("release", "com.example.app", "app"))
        self.assertEqual(self.dl.find_apk(self.project, variant="debug")["variant"], "debug")

    def test_module_filter(self):
        write_apk(self.project / "app", "debug", "com.example.app")
        write_apk(self.project / "demo" / "sample", "debug", "com.example.sample")
        self.assertEqual(self.dl.find_apk(self.project, module=":demo:sample")["package_name"],
                         "com.example.sample")
        self.assertEqual(self.dl.find_apk(self.project, module="app")["package_name"], "com.example.app")

    def test_nothing_assembled(self):
        with self.assertRaises(self.dl.LeaseError):
            self.dl.find_apk(self.project)

    def test_install_pins_the_leased_serial_and_launches(self):
        self.devices = ["S1", "S2"]
        self.dl.try_acquire(self.b)
        adb, log = fake_adb(self.root, ["S1", "S2"])
        os.environ["AHA_ADB"] = str(adb)
        apk = write_apk(self.project / "app", "debug", "com.example.app")
        result = self.dl.install(launch=True, wait=0)
        self.assertEqual((result["status"], result["serial"], result["launched"]), ("ok", "S2", True))
        self.assertEqual(result["apk"]["package_name"], "com.example.app")
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(calls[0], ["-s", "S2", "install", "-r", "-d", str(apk)])
        self.assertEqual(calls[1][:3], ["-s", "S2", "shell"])
        self.assertIn("com.example.app", calls[1])

    def test_install_when_busy_does_not_touch_adb(self):
        self.devices = ["S1"]
        self.dl.try_acquire(self.b)
        adb, log = fake_adb(self.root, ["S1"])
        os.environ["AHA_ADB"] = str(adb)
        write_apk(self.project / "app", "debug", "com.example.app")
        self.assertEqual(self.dl.install(wait=0)["status"], "busy")
        self.assertFalse(log.exists())

    def test_cli_exit_codes(self):
        adb, _ = fake_adb(self.root, [])
        env = {**os.environ, "AHA_ADB": str(adb)}
        script = ROOT / "assets" / "compose" / ".agents" / "scripts" / "device_lease.py"
        res = subprocess.run([sys.executable, str(script), "acquire", "--json"],
                             capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 3, res.stderr)
        self.assertEqual(json.loads(res.stdout)["status"], "no_device")
        res = subprocess.run([sys.executable, str(script), "serial"], capture_output=True, text=True, env=env)
        self.assertEqual(res.returncode, 1)


class TestDeviceGate(unittest.TestCase):
    def test_self_test_passes_in_both_tracks(self):
        for track in TRACKS:
            hook = ROOT / "assets" / track / ".agents" / "hooks" / "device_gate.py"
            res = subprocess.run([sys.executable, str(hook), "--self-test"], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{track}:\n{res.stdout}{res.stderr}")
            self.assertIn(" 0 failed", res.stdout)

    def test_no_andrun_or_scrcpy_left_in_the_payload(self):
        for track in TRACKS:
            agents = ROOT / "assets" / track / ".agents"
            self.assertFalse((agents / "hooks" / "scrcpy_daemon.py").exists())
            for path in agents.rglob("*"):
                if not path.is_file() or "references" in path.parts or path.suffix not in (".py", ".md", ".json"):
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore").lower()
                self.assertNotIn("andrun", text, path)
                self.assertNotIn("scrcpy", text, path)


class TestWorktreesEndToEnd(unittest.TestCase):
    """Two worktrees of one repo, one attached device, the installed hooks between them."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for cmd in (["git", "init", "-q"], ["git", "config", "user.name", "T"],
                    ["git", "config", "user.email", "t@example.com"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)
        (self.repo / "README").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "README"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True, capture_output=True)
        adb, _ = fake_adb(self.root, ["S1"])
        self.env = {**os.environ, "AHA_HOME": str(self.root / "home"), "AHA_ADB": str(adb)}
        self.env.pop("AHA_DEVICE", None)

    def tearDown(self):
        self.temp.cleanup()

    def aha(self, *args, cwd):
        return subprocess.run([sys.executable, str(AHA_SCRIPT), *args], cwd=cwd,
                              capture_output=True, text=True, env=self.env)

    def gate(self, worktree, event, payload):
        hook = worktree / ".agents" / "hooks" / "device_gate.py"
        res = subprocess.run([sys.executable, str(hook), event], input=json.dumps(payload),
                             capture_output=True, text=True, env=self.env, cwd=worktree / ".agents")
        return json.loads(res.stdout)

    def test_worktree_add_installs_the_same_harness(self):
        res = self.aha("init", "--track", "compose", "--profile", "android",
                       "--verifier-mode", "full", cwd=self.repo)
        self.assertEqual(res.returncode, 0, res.stderr)
        res = self.aha("worktree", "add", "../wt", "-b", "feat/x", cwd=self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        wt = self.root / "wt"
        manifest = json.loads((wt / ".agents" / ".aha.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["track"], manifest["profile"], manifest["verifier_mode"]),
                         ("compose", "android", "full"))
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=wt, capture_output=True, text=True)
        self.assertEqual(branch.stdout.strip(), "feat/x")

        # One device, two worktrees: the first one to touch it holds it.
        cmd = {"toolCall": {"name": "run_command", "args": {"CommandLine": "adb shell ls"}},
               "conversationId": "conv-a"}
        held = self.gate(self.repo, "pretooluse", cmd)
        self.assertEqual(held["overwrite"]["CommandLine"], "adb -s S1 shell ls")
        tap = {"toolCall": {"name": "mcp__mobilerun__tap_text", "args": {"text": "OK"}},
               "conversationId": "conv-b"}
        denied = self.gate(wt, "pretooluse", tap)
        self.assertEqual(denied["decision"], "deny")
        self.assertIn("acquire --wait", denied["reason"])

        # The holder's last session stopping hands the device over.
        self.assertEqual(self.gate(self.repo, "stop", {"conversationId": "conv-a"}), {"decision": "stop"})
        pinned = self.gate(wt, "pretooluse", tap)
        self.assertEqual(pinned["overwrite"], {"device": "S1"})

    def test_worktree_add_leaves_a_committed_claude_install_alone(self):
        res = self.aha("init", "--platform", "claude", cwd=self.repo)
        self.assertEqual(res.returncode, 0, res.stderr)
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "harness"], cwd=self.repo, check=True, capture_output=True)
        res = self.aha("worktree", "add", "../wt", "-b", "feat/y", cwd=self.repo)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("came with the checkout", res.stdout)
        local = json.loads((self.root / "wt" / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual(local["disabledMcpjsonServers"], ["mobilerun"])  # default verifier is compact

    def test_worktree_add_without_a_harness_fails(self):
        res = self.aha("worktree", "add", "../wt", cwd=self.repo)
        self.assertNotEqual(res.returncode, 0)
        self.assertFalse((self.root / "wt").exists())


if __name__ == "__main__":
    unittest.main()
