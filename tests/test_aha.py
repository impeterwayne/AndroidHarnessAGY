import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Path to the aha.py script under test
AHA_SCRIPT = Path(__file__).resolve().parent.parent / "aha.py"


def run_aha(*args, cwd=None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(AHA_SCRIPT), *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


class TestAhaExcludeAndUndo(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target = Path(self.temp_dir.name)
        # Initialize target as a git repo
        subprocess.run(["git", "init"], cwd=self.target, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.target, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=self.target, check=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_with_overlapping_files_and_git_exclude(self):
        # 1. Create a custom pre-existing user file in .agents/
        custom_file = self.target / ".agents" / "custom" / "my_tool.py"
        custom_file.parent.mkdir(parents=True, exist_ok=True)
        custom_file.write_text("print('custom')", encoding="utf-8")

        # 2. Add existing user exclude entry in .git/info/exclude
        exclude_file = self.target / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(parents=True, exist_ok=True)
        initial_exclude_content = "# Pre-existing comment\n*.user_ignore\n"
        exclude_file.write_text(initial_exclude_content, encoding="utf-8")

        # 3. Run `aha init --force` with default target (CWD = target)
        res = run_aha("init", "--force", "--profile", "minimal", cwd=self.target)
        self.assertEqual(res.returncode, 0, f"aha init failed: {res.stderr}")

        # Check installed files and manifest
        target_agents = self.target / ".agents"
        self.assertTrue((target_agents / ".aha.json").is_file())
        self.assertTrue(custom_file.is_file())

        # Check .git/info/exclude
        exclude_text = exclude_file.read_text(encoding="utf-8")
        self.assertIn("# Pre-existing comment", exclude_text)
        self.assertIn("*.user_ignore", exclude_text)
        self.assertIn("# <!-- aha:exclude:start -->", exclude_text)
        self.assertIn("# <!-- aha:exclude:end -->", exclude_text)
        self.assertIn("/.agents/.aha.json", exclude_text)

        # MUST NOT exclude the whole folder
        self.assertNotIn("\n/.agents/\n", exclude_text)
        self.assertNotIn("\n.agents/\n", exclude_text)
        self.assertNotIn("\n/.agents\n", exclude_text)

        # The custom file should NOT be in the exclude list
        self.assertNotIn("my_tool.py", exclude_text)

        # Check git status: custom_file should be untracked ('??'), but harness files should NOT appear
        git_status = subprocess.run(
            ["git", "status", "--porcelain", "-uall"], cwd=self.target, capture_output=True, text=True, check=True
        ).stdout
        self.assertIn(".agents/custom/my_tool.py", git_status)
        self.assertNotIn(".agents/rules/", git_status)
        self.assertNotIn(".agents/.aha.json", git_status)

        # Check git check-ignore
        ci_harness = subprocess.run(["git", "check-ignore", ".agents/.aha.json"], cwd=self.target, capture_output=True)
        self.assertEqual(ci_harness.returncode, 0, "Harness manifest should be ignored by git")
        ci_custom = subprocess.run(["git", "check-ignore", ".agents/custom/my_tool.py"], cwd=self.target, capture_output=True)
        self.assertEqual(ci_custom.returncode, 1, "Custom user file must NOT be ignored by git")

        # 4. Dry-run undo
        res_dry = run_aha("undo", "--dry-run", cwd=self.target)
        self.assertEqual(res_dry.returncode, 0)
        self.assertIn("would delete", res_dry.stdout)
        self.assertIn("preserve", res_dry.stdout)
        # Verify files were NOT deleted
        self.assertTrue((target_agents / ".aha.json").is_file())
        self.assertTrue(custom_file.is_file())

        # 5. Run `aha undo`
        res_undo = run_aha("undo", cwd=self.target)
        self.assertEqual(res_undo.returncode, 0, f"aha undo failed: {res_undo.stderr}")
        self.assertIn("preserved", res_undo.stdout)

        # Manifest and installed files should be deleted
        self.assertFalse((target_agents / ".aha.json").is_file())
        self.assertFalse((target_agents / "rules" / "lean.md").is_file())

        # Overlapping custom file MUST still exist and .agents/ MUST be preserved
        self.assertTrue(custom_file.is_file())
        self.assertTrue(target_agents.is_dir())

        # Exclude block must be removed from .git/info/exclude
        clean_exclude = exclude_file.read_text(encoding="utf-8")
        self.assertNotIn("# <!-- aha:exclude:start -->", clean_exclude)
        self.assertNotIn("# <!-- aha:exclude:end -->", clean_exclude)
        self.assertNotIn("/.agents/.aha.json", clean_exclude)
        # Pre-existing entries must be preserved
        self.assertIn("# Pre-existing comment", clean_exclude)
        self.assertIn("*.user_ignore", clean_exclude)

        # AGENTS.md should be deleted (since it was created by init and only had our block)
        self.assertFalse((self.target / "AGENTS.md").exists())

    def test_undo_init_alias_and_clean_removal_when_no_overlap(self):
        # When there are no overlapping files, undo should completely delete .agents/
        res_init = run_aha("init", str(self.target), "--profile", "minimal")
        self.assertEqual(res_init.returncode, 0)
        self.assertTrue((self.target / ".agents").is_dir())

        # Use undo-init alias with explicit target
        res_undo = run_aha("undo-init", str(self.target))
        self.assertEqual(res_undo.returncode, 0)
        self.assertFalse((self.target / ".agents").exists())

    def test_agents_md_splicing_and_unsplicing(self):
        # Target has existing AGENTS.md with user instructions
        root_doc = self.target / "AGENTS.md"
        user_content = "# My Project Notes\nDo not break this."
        root_doc.write_text(user_content, encoding="utf-8")

        # Run init
        res_init = run_aha("init", "--profile", "minimal", cwd=self.target)
        self.assertEqual(res_init.returncode, 0)
        spliced_text = root_doc.read_text(encoding="utf-8")
        self.assertIn("# My Project Notes", spliced_text)
        self.assertIn("<!-- aha:orchestrate:start -->", spliced_text)

        # Run undo
        res_undo = run_aha("undo", cwd=self.target)
        self.assertEqual(res_undo.returncode, 0)
        restored_text = root_doc.read_text(encoding="utf-8").strip()
        self.assertEqual(restored_text, user_content)

    def test_update_status_and_remove_alias(self):
        # Init with minimal profile
        res_init = run_aha("init", cwd=self.target, *["--profile", "minimal"])
        self.assertEqual(res_init.returncode, 0)

        # Add custom overlapping file
        custom_file = self.target / ".agents" / "custom_skill.md"
        custom_file.write_text("my skill", encoding="utf-8")

        # Check status (default target '.')
        res_status = run_aha("status", cwd=self.target)
        self.assertEqual(res_status.returncode, 0)
        self.assertIn("aha status", res_status.stdout)

        # Update profile to figma (default target '.')
        res_update = run_aha("update", "--profile", "figma", cwd=self.target)
        self.assertEqual(res_update.returncode, 0)
        self.assertTrue(custom_file.is_file())

        # Remove using `remove` alias (default target '.')
        res_remove = run_aha("remove", cwd=self.target)
        self.assertEqual(res_remove.returncode, 0)
        self.assertTrue(custom_file.is_file())
        self.assertTrue((self.target / ".agents").is_dir())

    def test_local_modifications_protection(self):
        res_init = run_aha("init", str(self.target), "--profile", "minimal")
        self.assertEqual(res_init.returncode, 0)

        # Modify an installed file
        manifest_file = self.target / ".agents" / ".aha.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        first_rel = next(k for k in manifest["files"] if not k.startswith(".."))
        installed_file = self.target / ".agents" / first_rel
        installed_file.write_text("local modification", encoding="utf-8")

        # Attempt undo without --force: must fail and refuse to delete
        res_undo = run_aha("undo", str(self.target))
        self.assertNotEqual(res_undo.returncode, 0)
        self.assertIn("refusing to delete local edits", res_undo.stderr)
        self.assertTrue(installed_file.is_file())

        # Now pass --force: should proceed
        res_force = run_aha("undo", str(self.target), "--force")
        self.assertEqual(res_force.returncode, 0)
        self.assertFalse((self.target / ".agents").exists())

    def test_no_git_exclude_flag(self):
        res = run_aha("init", "--no-git-exclude", "--profile", "minimal", cwd=self.target)
        self.assertEqual(res.returncode, 0)
        exclude_file = self.target / ".git" / "info" / "exclude"
        if exclude_file.is_file():
            self.assertNotIn("# <!-- aha:exclude:start -->", exclude_file.read_text(encoding="utf-8"))


class TestTracks(unittest.TestCase):
    """The two payloads are separate trees; `--track` picks one and only one."""

    ASSETS = AHA_SCRIPT.parent / "assets"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target = Path(self.temp_dir.name)
        subprocess.run(["git", "init"], cwd=self.target, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.target, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=self.target, check=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _manifest(self):
        return json.loads((self.target / ".agents" / ".aha.json").read_text(encoding="utf-8"))

    def _rules(self):
        return sorted(p.name for p in (self.target / ".agents" / "rules").iterdir())

    def _agents(self):
        return sorted(p.name for p in (self.target / ".agents" / "agents").iterdir())

    def test_default_track_is_xml(self):
        res = run_aha("init", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._manifest()["track"], "xml")
        self.assertIn("xml.md", self._rules())
        self.assertNotIn("android.md", self._rules())
        self.assertIn("figma-xml-developer.md", self._agents())
        self.assertNotIn("figma-compose-developer.md", self._agents())

    def test_xml_track_installs_only_xml_payload(self):
        res = run_aha("init", "--track", "xml", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._manifest()["track"], "xml")
        self.assertIn("xml.md", self._rules())
        self.assertNotIn("android.md", self._rules())
        self.assertIn("figma-xml-developer.md", self._agents())
        self.assertNotIn("figma-compose-developer.md", self._agents())

        skills = {p.name for p in (self.target / ".agents" / "skills").iterdir()}
        self.assertIn("shape-view", skills)
        self.assertIn("image-loading-glide", skills)
        self.assertIn("android-xml-views", skills)
        self.assertIn("figma2xml", skills)
        # Nothing Compose-only leaks in.
        self.assertFalse(
            {s for s in skills if s.startswith("compose-")} | {
                "image-loading-landscapist", "orbit-mvi-feature-builder", "figma2compose",
            } & skills)

    def test_compose_track_installs_only_compose_payload(self):
        res = run_aha("init", "--track", "compose", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self._manifest()["track"], "compose")
        self.assertIn("android.md", self._rules())
        self.assertNotIn("xml.md", self._rules())
        self.assertIn("figma-compose-developer.md", self._agents())
        self.assertNotIn("figma-xml-developer.md", self._agents())

        skills = {p.name for p in (self.target / ".agents" / "skills").iterdir()}
        self.assertIn("orbit-mvi-feature-builder", skills)
        self.assertIn("image-loading-landscapist", skills)
        self.assertIn("figma2compose", skills)
        # Nothing XML-only leaks in.
        self.assertFalse(
            {"shape-view", "image-loading-glide", "android-xml-views", "figma2xml"} & skills)

    def test_update_carries_the_track_forward(self):
        run_aha("init", "--track", "compose", "--profile", "android", "--no-git-exclude", cwd=self.target)
        res = run_aha("update", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        # A flagless update must not silently swap the project's always-on rules.
        self.assertEqual(self._manifest()["track"], "compose")
        self.assertEqual(self._manifest()["profile"], "android")
        self.assertIn("android.md", self._rules())

    def test_unknown_track_is_rejected(self):
        res = run_aha("init", "--track", "flutter", "--no-git-exclude", cwd=self.target)
        self.assertNotEqual(res.returncode, 0)

    def test_tracks_never_ship_both_ui_rules(self):
        for track in ("compose", "xml"):
            rules = {p.name for p in (self.ASSETS / track / ".agents" / "rules").iterdir()}
            self.assertEqual(
                len(rules & {"android.md", "xml.md"}), 1,
                f"{track} must ship exactly one always-on UI rule, has {rules}")

    def test_shared_files_stay_byte_identical(self):
        """Files common to both trees are duplicated on purpose. Catch the drift."""
        compose = self.ASSETS / "compose" / ".agents"
        xml = self.ASSETS / "xml" / ".agents"

        # Deliberately divergent: each states its own toolkit's rules and roster.
        divergent = {
            "rules/figma.md",
            "rules/lean.md",
            "agents/orchestrator.md",
            "agents/executor.md",
            "agents/explore.md",
            "agents/oracle.md",
            "agents/verifier.md",
            "agents/figma-analyzer.md",
            "agents/figma-asset-extractor.md",
        }
        divergent_prefixes = ("skills/figma-design-analyzer/", "skills/figma-asset-extractor/",
                              "skills/lean/", "skills/code-review/", "skills/kotlin-api-design/",
                              "skills/kotlin-concurrency-and-flow/")

        mismatched = []
        for src in compose.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(compose).as_posix()
            if rel in divergent or rel.startswith(divergent_prefixes):
                continue
            twin = xml / rel
            if not twin.is_file():
                continue  # track-specific file, not a shared one
            if src.read_bytes() != twin.read_bytes():
                mismatched.append(rel)

        self.assertEqual(
            mismatched, [],
            "shared payload files have drifted between tracks:\n  " + "\n  ".join(mismatched))

    def test_hooks_and_loop_engine_are_shared(self):
        compose = self.ASSETS / "compose" / ".agents"
        xml = self.ASSETS / "xml" / ".agents"
        for rel in ("hooks.json", "mcp_config.json", "scripts/loop.py",
                    "hooks/rule_gate.py", "hooks/write_guard.py", "hooks/device_gate.py",
                    "hooks/stop_verifier.py", "hooks/intent_gate.py", "hooks/scrcpy_daemon.py"):
            self.assertEqual(
                (compose / rel).read_bytes(), (xml / rel).read_bytes(),
                f"{rel} differs between tracks")


class TestClaudePlatform(unittest.TestCase):
    AGY_TOOLS = ("view_file", "write_to_file", "replace_file_content", "grep_search",
                 "list_dir", "run_command", "invoke_subagent", "send_message", "manage_subagents")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target = Path(self.temp_dir.name)
        subprocess.run(["git", "init"], cwd=self.target, capture_output=True, check=True)
        self.claude = self.target / ".claude"

    def tearDown(self):
        self.temp_dir.cleanup()

    def init(self, *extra):
        res = run_aha("init", "--platform", "claude", *extra, cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        return res

    def frontmatter(self, agent):
        text = (self.claude / "agents" / f"{agent}.md").read_text(encoding="utf-8")
        return text.split("---")[1]

    def test_installs_into_claude_layout_without_git_exclude(self):
        self.init()
        self.assertTrue((self.claude / ".aha.json").is_file())
        self.assertTrue((self.claude / "skills" / "lean" / "SKILL.md").is_file())
        self.assertTrue((self.claude / "rules" / "xml.md").is_file())
        self.assertTrue((self.claude / "hooks" / "claude_adapter.py").is_file())
        self.assertFalse((self.claude / "hooks.json").exists())
        self.assertFalse((self.target / ".agents").exists())
        self.assertFalse((self.target / "AGENTS.md").exists())

        exclude = self.target / ".git" / "info" / "exclude"
        self.assertNotIn("aha:exclude", exclude.read_text(encoding="utf-8") if exclude.is_file() else "")
        status = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=self.target,
                                capture_output=True, text=True, check=True).stdout
        self.assertIn(".claude/agents/executor.md", status)
        self.assertIn("CLAUDE.md", status)

    def test_subagents_use_sonnet_and_planners_opus(self):
        self.init()
        for agent in ("executor", "explore", "verifier", "figma-analyzer"):
            self.assertIn("model: sonnet", self.frontmatter(agent), agent)
        for agent in ("orchestrator", "oracle"):
            self.assertIn("model: opus", self.frontmatter(agent), agent)
        executor = self.frontmatter("executor")
        self.assertIn("tools: Read, Write, Edit, Grep, Glob, Bash", executor)
        self.assertNotIn("subagent:", executor)
        self.assertIn("tools: Read, Grep, Glob, Agent", self.frontmatter("orchestrator"))
        self.assertNotIn("mainAgent", self.frontmatter("orchestrator"))
        self.assertNotIn("tools:", self.frontmatter("figma-analyzer"))  # needs MCP tools

    def test_subagent_model_flag_is_carried_by_update(self):
        self.init("--subagent-model", "haiku")
        self.assertIn("model: haiku", self.frontmatter("executor"))
        self.assertIn("model: opus", self.frontmatter("oracle"))
        res = run_aha("update", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("model: haiku", self.frontmatter("executor"))

    def test_rendered_text_speaks_claude(self):
        self.init()
        doc = (self.target / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aha:orchestrate:start -->", doc)
        for token in self.AGY_TOOLS + (".agents/", "hooks.json", "`Subagents`"):
            self.assertNotIn(token, doc)
        for rel in ("agents/executor.md", "rules/xml.md", "skills/ultrawork/SKILL.md"):
            text = (self.claude / rel).read_text(encoding="utf-8")
            self.assertNotIn(".agents/", text, rel)

    def test_settings_and_mcp_merge_and_undo_restores_them(self):
        self.claude.mkdir()
        user_settings = {"permissions": {"allow": ["Bash(ls)"]},
                         "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        (self.claude / "settings.json").write_text(json.dumps(user_settings), encoding="utf-8")
        (self.target / ".mcp.json").write_text(json.dumps({"mcpServers": {"mine": {"command": "x"}}}),
                                               encoding="utf-8")
        (self.target / "CLAUDE.md").write_text("# Mine\n", encoding="utf-8")
        self.init()

        settings = json.loads((self.claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["permissions"], user_settings["permissions"])
        commands = [h["command"] for entries in settings["hooks"].values()
                    for e in entries for h in e["hooks"]]
        self.assertIn("echo mine", commands)
        self.assertTrue(any("claude_adapter.py\" PreToolUse write_guard.py" in c for c in commands))
        self.assertTrue(any("SessionStart" in c for c in commands))
        mcp = json.loads((self.target / ".mcp.json").read_text(encoding="utf-8"))
        self.assertIn("mine", mcp["mcpServers"])
        self.assertIn("figma-mcp-android", mcp["mcpServers"])

        # A second update must not stack a second copy of every hook.
        run_aha("update", cwd=self.target)
        again = json.loads((self.claude / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(again, settings)

        res = run_aha("undo", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads((self.claude / "settings.json").read_text(encoding="utf-8")),
                         user_settings)
        self.assertEqual(json.loads((self.target / ".mcp.json").read_text(encoding="utf-8")),
                         {"mcpServers": {"mine": {"command": "x"}}})
        self.assertEqual((self.target / "CLAUDE.md").read_text(encoding="utf-8"), "# Mine\n")
        self.assertFalse((self.claude / "agents").exists())

    def test_existing_claude_files_are_kept(self):
        mine = self.claude / "agents" / "executor.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("my own executor\n", encoding="utf-8")
        res = self.init()
        self.assertIn("kept yours", res.stdout)
        self.assertEqual(mine.read_text(encoding="utf-8"), "my own executor\n")
        run_aha("undo", cwd=self.target)
        self.assertEqual(mine.read_text(encoding="utf-8"), "my own executor\n")

    def test_both_platforms_side_by_side(self):
        self.assertEqual(run_aha("init", "--no-git-exclude", cwd=self.target).returncode, 0)
        self.init()
        self.assertNotEqual(run_aha("status", cwd=self.target).returncode, 0)  # ambiguous
        res = run_aha("undo", "--platform", "claude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((self.target / ".agents" / ".aha.json").is_file())
        self.assertTrue((self.target / "AGENTS.md").is_file())

    def adapter(self, *argv, payload):
        res = subprocess.run([sys.executable, str(self.claude / "hooks" / "claude_adapter.py"), *argv],
                             input=json.dumps(payload), capture_output=True, text=True,
                             env={**os.environ, "CLAUDE_PROJECT_DIR": str(self.target)})
        self.assertEqual(res.returncode, 0, res.stderr)
        return json.loads(res.stdout)

    def test_adapter_translates_hook_contract(self):
        self.init()
        kt = str(self.target / "app" / "A.kt")
        write = {"session_id": "s1", "tool_name": "Write",
                 "tool_input": {"file_path": kt, "content": "fun a() = 1\n"}}
        denied = self.adapter("PreToolUse", "write_guard.py", payload=write)
        self.assertEqual(denied["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("Agent(subagent_type='executor')",
                      denied["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertEqual(self.adapter("PreToolUse", "write_guard.py",
                                      payload={**write, "agent_type": "executor"}), {})

        edit = {"session_id": "s1", "tool_name": "Edit",
                "tool_input": {"file_path": kt, "old_string": "1", "new_string": "2 // why"}}
        linted = self.adapter("PreToolUse", "rule_gate.py", payload=edit)
        self.assertEqual(linted["hookSpecificOutput"]["permissionDecision"], "deny")
        clean = {**edit, "tool_input": {**edit["tool_input"], "new_string": "2"}}
        self.assertEqual(self.adapter("PreToolUse", "rule_gate.py", payload=clean), {})

        armed = self.adapter("UserPromptSubmit", "intent_gate.py",
                             payload={"session_id": "s1", "prompt": "ultrawork: fix login"})
        context = armed["hookSpecificOutput"]["additionalContext"]
        self.assertIn(".claude/skills/ultrawork/SKILL.md", context)
        self.assertNotIn("view_file", context)
        self.assertEqual(self.adapter("UserPromptSubmit", "intent_gate.py",
                                      payload={"session_id": "s1", "prompt": "fix login"}), {})
        self.assertEqual(self.adapter("Stop", "stop_verifier.py", payload={"session_id": "s1"}), {})
        self.assertFalse(list(self.claude.rglob("__pycache__")))


class TestVerifierModesAndMobilerun(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target = Path(self.temp_dir.name)
        subprocess.run(["git", "init"], cwd=self.target, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.target, check=True)
        subprocess.run(["git", "config", "user.email", "tester@example.com"], cwd=self.target, check=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _manifest(self, platform="antigravity"):
        p = self.target / (".claude" if platform == "claude" else ".agents") / ".aha.json"
        return json.loads(p.read_text(encoding="utf-8"))

    def test_default_verifier_mode_is_compact(self):
        res = run_aha("init", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        manifest = self._manifest()
        self.assertEqual(manifest.get("verifier_mode"), "compact")
        verifier_md = (self.target / ".agents" / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("### Active Mode: compact", verifier_md)

    def test_init_with_verifier_mode_flag(self):
        for mode in ("minimal", "compact", "full"):
            res = run_aha("init", "--force", "--verifier-mode", mode, "--no-git-exclude", cwd=self.target)
            self.assertEqual(res.returncode, 0, res.stderr)
            manifest = self._manifest()
            self.assertEqual(manifest.get("verifier_mode"), mode)
            verifier_md = (self.target / ".agents" / "agents" / "verifier.md").read_text(encoding="utf-8")
            self.assertIn(f"### Active Mode: {mode}", verifier_md)

        # Also test --verifier alias flag for init full
        res_alias = run_aha("init", "--force", "--verifier", "full", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res_alias.returncode, 0, res_alias.stderr)
        self.assertEqual(self._manifest().get("verifier_mode"), "full")
        verifier_md = (self.target / ".agents" / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("### Active Mode: full", verifier_md)

    def test_aha_verifier_command_get_and_set(self):
        res_init = run_aha("init", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res_init.returncode, 0, res_init.stderr)

        # Query active mode (default is compact)
        res_get = run_aha("verifier", cwd=self.target)
        self.assertEqual(res_get.returncode, 0, res_get.stderr)
        self.assertIn("verifier mode: compact", res_get.stdout)

        # Switch to minimal
        res_set = run_aha("verifier", "minimal", cwd=self.target)
        self.assertEqual(res_set.returncode, 0, res_set.stderr)
        self.assertIn("verifier mode set to: minimal", res_set.stdout)
        self.assertEqual(self._manifest().get("verifier_mode"), "minimal")
        verifier_md = (self.target / ".agents" / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("### Active Mode: minimal", verifier_md)

        # Switch to full
        res_set2 = run_aha("verifier", "full", cwd=self.target)
        self.assertEqual(res_set2.returncode, 0, res_set2.stderr)
        self.assertIn("verifier mode set to: full", res_set2.stdout)
        self.assertEqual(self._manifest().get("verifier_mode"), "full")
        verifier_md = (self.target / ".agents" / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("### Active Mode: full", verifier_md)

        # Invalid mode is rejected
        res_invalid = run_aha("verifier", "bogus", cwd=self.target)
        self.assertNotEqual(res_invalid.returncode, 0)

    def test_aha_update_preserves_verifier_mode(self):
        res_init = run_aha("init", "--verifier", "full", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res_init.returncode, 0, res_init.stderr)
        self.assertEqual(self._manifest().get("verifier_mode"), "full")

        res_update = run_aha("update", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res_update.returncode, 0, res_update.stderr)
        self.assertEqual(self._manifest().get("verifier_mode"), "full")
        verifier_md = (self.target / ".agents" / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("### Active Mode: full", verifier_md)

    def test_mobilerun_installed_and_scrcpy_absent(self):
        res = run_aha("init", "--profile", "android", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        skills = {p.name for p in (self.target / ".agents" / "skills").iterdir()}
        self.assertIn("mobilerun", skills)
        self.assertNotIn("scrcpy", skills)
        self.assertTrue((self.target / ".agents" / "skills" / "mobilerun" / "SKILL.md").is_file())
        self.assertTrue((self.target / ".agents" / "skills" / "mobilerun" / "references" / "tools_reference.md").is_file())

        mcp_cfg = json.loads((self.target / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertIn("mobilerun", mcp_cfg.get("mcpServers", {}))
        self.assertNotIn("scrcpy", mcp_cfg.get("mcpServers", {}))
        self.assertEqual(mcp_cfg["mcpServers"]["mobilerun"]["command"], "npx")

    def test_device_serial_configuration(self):
        res = run_aha("init", "--device", "emulator-5554", "--no-git-exclude", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        manifest = self._manifest()
        self.assertEqual(manifest.get("device_serial"), "emulator-5554")
        mcp_cfg = json.loads((self.target / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertEqual(mcp_cfg["mcpServers"]["mobilerun"]["env"]["MOBILERUN_DEVICE"], "emulator-5554")

        # Update verifier with new device serial
        res_v = run_aha("verifier", "full", "--device", "device-9999", cwd=self.target)
        self.assertEqual(res_v.returncode, 0, res_v.stderr)
        manifest = self._manifest()
        self.assertEqual(manifest.get("device_serial"), "device-9999")
        mcp_cfg2 = json.loads((self.target / ".agents" / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertEqual(mcp_cfg2["mcpServers"]["mobilerun"]["env"]["MOBILERUN_DEVICE"], "device-9999")

    def test_claude_platform_verifier_mode_and_mobilerun(self):
        res = run_aha("init", "--platform", "claude", "--verifier-mode", "minimal", "--device", "pixel-7", cwd=self.target)
        self.assertEqual(res.returncode, 0, res.stderr)
        manifest = self._manifest(platform="claude")
        self.assertEqual(manifest.get("verifier_mode"), "minimal")
        self.assertEqual(manifest.get("device_serial"), "pixel-7")

        verifier_md = (self.target / ".claude" / "agents" / "verifier.md").read_text(encoding="utf-8")
        self.assertIn("### Active Mode: minimal", verifier_md)
        # verifier should NOT have tools: restricted so it can invoke MCP
        self.assertNotIn("tools:", verifier_md.split("---")[1])

        mcp_cfg = json.loads((self.target / ".mcp.json").read_text(encoding="utf-8"))
        self.assertIn("mobilerun", mcp_cfg.get("mcpServers", {}))
        self.assertEqual(mcp_cfg["mcpServers"]["mobilerun"]["env"]["MOBILERUN_DEVICE"], "pixel-7")


if __name__ == "__main__":
    unittest.main()
