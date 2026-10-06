#!/usr/bin/env python3
"""
aha -- inject the Antigravity Android agent harness into any project.

There are two payloads, one per UI toolkit, and they are independent trees:

    assets/compose/   Jetpack Compose -- rules/android.md, the compose-* skills,
                      Landscapist, Orbit MVI, figma-compose-developer
    assets/xml/       Views and XML layouts -- rules/xml.md, ShapeView, Glide,
                      Epoxy, figma-xml-developer

`--track` picks one and the whole of it is installed. They are never merged: the
thing that separates them is always-on prompt context, so shipping both would hand
the agent two contradictory sets of non-negotiables.

Within the selected track, `assets/<track>/.agents/` (rules, skills, agents, hooks,
mcp_config.json) lands at `<target>/.agents/`, and `assets/<track>/AGENTS.md`
carries the delegation rule, which must sit at the project root to be read reliably
-- it is written as a marker-delimited block, so an existing `AGENTS.md` keeps its
own content and `undo` / `remove` takes back only the block it added.

Installed files are excluded individually in `.git/info/exclude` under a marked
block on `init` and `update`, leaving any overlapping or custom files in `.agents/`
tracked by git.

`--platform claude` installs the same track for Claude Code instead: `.claude/`
(skills, rules, agents, hooks), `CLAUDE.md`, hooks wired into `.claude/settings.json`
through `hooks/claude_adapter.py`, MCP servers merged into `.mcp.json`. Nothing is
git-excluded -- a Claude install is meant to be committed. Subagents are pinned to
`--subagent-model` (default sonnet); orchestrator and oracle stay on opus.

    python aha.py init      [target]  copy the selected track into [target] (default: .)
    python aha.py update    [target]  re-copy, keeping locally edited files
    python aha.py status    [target]  what is installed, and what drifted
    python aha.py undo      [target]  cleanly reverses init, keeping non-AHA files
    python aha.py undo-init [target]  alias for undo
    python aha.py remove    [target]  alias for undo
    python aha.py list                available components and profiles
    python aha.py verifier [mode]     this worktree's verifier mode (and --device)
    python aha.py mcp [on|off <name>]  harness MCP servers (mobilerun follows the verifier)
    python aha.py worktree add <path> [git args]
                                      git worktree add, then install the same harness

    aha init                          Views and XML layouts (the default)
    aha init --track compose          Jetpack Compose
    aha init --platform claude        Claude Code instead of Antigravity

Stdlib only. Run `python aha.py <command> --help` for flags.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# The payload is an asset, not this repo's own setup: `assets/<track>/` holds the
# one copy of every file that ships, and this repo has no `.agents/` of its own.
#
# Files common to both tracks -- the hooks, loop.py, mcp_config.json and the
# toolkit-neutral skills -- are duplicated by design so each tree installs whole.
# `tests/test_aha.py` asserts they stay byte-identical and fails on drift.
REPO_ROOT = Path(__file__).resolve().parent
ASSETS_ROOT = REPO_ROOT / "assets"
TRACKS = ("xml", "compose")
DEFAULT_TRACK = "xml"

# Rebound by select_track() before any command touches them.
SOURCE_ROOT = ASSETS_ROOT / DEFAULT_TRACK
SOURCE_AGENTS = SOURCE_ROOT / ".agents"
MANIFEST_NAME = ".aha.json"
LEGACY_MANIFEST_NAME = ".oma.json"

# The delegation rule lives at the project root rather than in `.agents/rules/`:
# rule files load unreliably, `AGENTS.md` is always read. Manifest keys are
# relative to `<target>/.agents/`, so this one is recorded as `../AGENTS.md`.
ROOT_DOC = "AGENTS.md"
ROOT_DOC_KEY = "../" + ROOT_DOC
BLOCK_START = "<!-- aha:orchestrate:start -->"
BLOCK_END = "<!-- aha:orchestrate:end -->"
LEGACY_BLOCK_START = "<!-- oma:orchestrate:start -->"
LEGACY_BLOCK_END = "<!-- oma:orchestrate:end -->"
EXCLUDE_BLOCK_START = "# <!-- aha:exclude:start -->"
EXCLUDE_BLOCK_END = "# <!-- aha:exclude:end -->"
LEGACY_EXCLUDE_BLOCK_START = "# <!-- oma:exclude:start -->"
LEGACY_EXCLUDE_BLOCK_END = "# <!-- oma:exclude:end -->"

# Where the harness lands in the target, and which root doc carries the delegation
# rule. Rebound by select_platform() alongside ROOT_DOC / ROOT_DOC_KEY above.
PLATFORMS = ("antigravity", "claude")
DEFAULT_PLATFORM = "antigravity"
PLATFORM = DEFAULT_PLATFORM
HARNESS_DIR = ".agents"
PLATFORM_LAYOUT = {
    "antigravity": (".agents", "AGENTS.md"),
    "claude": (".claude", "CLAUDE.md"),
}

VERIFIER_MODES = ("minimal", "compact", "full")
DEFAULT_VERIFIER_MODE = "compact"
VERIFIER_MODE = DEFAULT_VERIFIER_MODE

# Per-worktree settings live under <harness>/state/, which is never installed,
# never recorded in the manifest, and git-ignored by a `.gitignore` written beside
# them -- so a committed Claude install stays identical across worktrees while
# each one runs its own verifier mode and prefers its own device.
LOCAL_STATE_DIR = "state"
LOCAL_VERIFIER_MODE = "verifier_mode"
LOCAL_DEVICE = "device"

# mobilerun follows the verifier: on in a worktree whose mode is `full`, off in
# every other. The optional servers (figma-mcp-android) ship when something
# installed uses them; `--mcp` picks them at install and `aha mcp on|off` toggles
# them later. The manifest records that choice as `mcp_servers` (mobilerun never
# in it), so `update` carries it forward. None means every optional server -- what
# installs from before the toggle existed received.
MOBILERUN = "mobilerun"
MCP_ALIASES = {"figma": "figma-mcp-android"}
MCP_SERVERS: list[str] | None = None
MOBILERUN_ON = False

VERIFIER_MODE_START = "<!-- aha:verifier-mode:start -->"
VERIFIER_MODE_END = "<!-- aha:verifier-mode:end -->"


def update_verifier_mode_in_text(text: str, mode: str) -> str:
    start = text.find(VERIFIER_MODE_START)
    end = text.find(VERIFIER_MODE_END)
    if start != -1 and end != -1 and end > start:
        replacement = f"{VERIFIER_MODE_START}\n### Active Mode: {mode}\n{VERIFIER_MODE_END}"
        return text[:start] + replacement + text[end + len(VERIFIER_MODE_END):]
    return text


def read_local_state(target_agents: Path, name: str) -> str | None:
    try:
        value = (target_agents / LOCAL_STATE_DIR / name).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def write_local_state(target_agents: Path, name: str, value: str | None) -> None:
    """Set (or with None, clear) one per-worktree setting under state/."""
    state = target_agents / LOCAL_STATE_DIR
    path = state / name
    if value is None:
        path.unlink(missing_ok=True)
        return
    state.mkdir(parents=True, exist_ok=True)
    ignore = state / ".gitignore"
    if not ignore.is_file():
        ignore.write_text("*\n", encoding="utf-8")
    path.write_text(value + "\n", encoding="utf-8")


# Claude Code only. Files that exist for Claude and not for Antigravity, keyed by
# their path under `.claude/`.
CLAUDE_OVERLAY = ASSETS_ROOT / "claude"
CLAUDE_ADAPTER = "hooks/claude_adapter.py"
CLAUDE_SETTINGS = "settings.json"
CLAUDE_MCP = ".mcp.json"
CLAUDE_LOCAL_SETTINGS = "settings.local.json"
# Planning stays on the strongest model; every worker defaults to --subagent-model.
CLAUDE_AGENT_MODELS = {"orchestrator": "opus", "oracle": "opus"}
DEFAULT_SUBAGENT_MODEL = "sonnet"
SUBAGENT_MODEL = DEFAULT_SUBAGENT_MODEL
CLAUDE_TOOLS = {
    "view_file": "Read",
    "write_to_file": "Write",
    "replace_file_content": "Edit",
    "multi_replace_file_content": "Edit",
    "grep_search": "Grep",
    "list_dir": "Glob",
    "run_command": "Bash",
    "invoke_subagent": "Agent",
}
# Prose renames on top of CLAUDE_TOOLS for text the agent reads.
CLAUDE_PROSE = {**CLAUDE_TOOLS, "send_message": "SendMessage",
                "manage_subagents": "background agents"}
CLAUDE_PROSE_RE = re.compile(r"\b(" + "|".join(sorted(CLAUDE_PROSE, key=len, reverse=True)) + r")\b")
AGENTS_PATH_RE = re.compile(r"(?<![\w.])\.agents(?=[/`\s'\")]|$)")
# Antigravity-only sentences in the root doc, and what Claude Code should read instead.
CLAUDE_ROOT_DOC_EDITS = (
    ("`Subagents` is an array, so N parallel spawns are one call.",
     "Several `Agent` calls in one message run in parallel, so N spawns are one turn."),
    ("You have no shell, so you cannot reproduce one either.",
     "Do not run Gradle yourself either — one shell holds it at a time."),
    ("`hooks.json` (deterministic gates)", "`settings.json` hooks (deterministic gates)"),
    ("Polling `manage_subagents`", "Polling background agents"),
)
# Antigravity hook events and the Claude Code events that carry the same moment.
CLAUDE_EVENTS = {"PreToolUse": "PreToolUse", "PreInvocation": "UserPromptSubmit", "Stop": "Stop"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".toml", ".yaml", ".yml", ".csv", ".txt", ".pftxt"}

# Directories and files that are development scaffolding for the harness repo
# itself and have no business in a target project.
EXCLUDES = (
    "state/*",
    "state",
    "**/__pycache__/*",
    "**/__pycache__",
    "*.pyc",
    MANIFEST_NAME,
    LEGACY_MANIFEST_NAME,
)

# Files whose contents are merged into an existing target file rather than
# overwritten, because a project may already have its own.
MERGEABLE = ("hooks.json", "mcp_config.json")

# Profiles select which skills/agents/rules ship WITHIN a track. `full` is the
# default and is defined by absence -- everything that track has on disk. The named
# subsets are convenience, not policy; edit these lists freely.
#
# The names mean the same thing in both tracks, so muscle memory carries across:
# `android` is app work without the Figma pipeline, `figma` is a design-to-code
# sprint, `minimal` is lean review and goal loops. Only the payload differs.
PROFILES: dict[str, dict[str, dict[str, list[str]]]] = {
    "compose": {
        "minimal": {
            "skills": [
                "lean", "lean-audit", "lean-debt", "lean-gain", "lean-help",
                "lean-review", "code-review", "document_project", "loop", "ultrawork",
                "gradle-run", "mobilerun",
            ],
            "agents": ["explore", "oracle", "orchestrator", "executor", "verifier"],
            "rules": ["lean"],
        },
        "figma": {
            "skills": [
                "figma-asset-extractor", "figma-design-analyzer", "figma2compose",
                "image-loading-landscapist", "styles", "lean", "lean-review",
                "android-code-indexer", "android-resource-policy",
                "compose-component-design", "compose-state-and-effects",
                "orbit-mvi-feature-builder", "gradle-run", "testing-setup", "mobilerun",
            ],
            "agents": [
                "explore", "figma-analyzer", "figma-asset-extractor",
                "figma-compose-developer", "orchestrator", "verifier",
            ],
            "rules": ["figma", "android", "lean"],
        },
        "android": {
            "skills": [
                "adaptive", "agp-9-upgrade", "android-code-indexer",
                "android-intent-security", "android-profiler", "android-resource-policy",
                "appfunctions", "code-review", "compose-animations",
                "compose-component-design", "compose-focus-navigation",
                "compose-performance", "compose-state-and-effects",
                "compose-ui-testing-patterns", "document_project", "edge-to-edge",
                "gradle-run", "image-loading-landscapist", "kotlin-api-design",
                "kotlin-compose-skills", "kotlin-concurrency-and-flow",
                "kotlin-control-flow", "lean", "lean-audit", "lean-debt", "lean-gain",
                "lean-help", "lean-review", "loop",
                "migrate-xml-views-to-jetpack-compose", "navigation-3",
                "orbit-mvi-feature-builder", "play-policy-insights", "r8-analyzer",
                "mobilerun", "styles", "testing-setup", "translate-strings", "ultrawork",
                "xxpermissions-ktx",
            ],
            "agents": ["explore", "oracle", "orchestrator", "executor", "verifier"],
            "rules": ["android", "lean"],
        },
    },
    "xml": {
        "minimal": {
            "skills": [
                "lean", "lean-audit", "lean-debt", "lean-gain", "lean-help",
                "lean-review", "code-review", "document_project", "loop", "ultrawork",
                "gradle-run", "mobilerun",
            ],
            "agents": ["explore", "oracle", "orchestrator", "executor", "verifier"],
            "rules": ["lean"],
        },
        "figma": {
            "skills": [
                "figma-asset-extractor", "figma-design-analyzer", "figma2xml",
                "shape-view", "image-loading-glide", "android-xml-views",
                "xml-resource-policy", "lean", "lean-review", "android-code-indexer",
                "gradle-run", "testing-setup", "mobilerun",
            ],
            "agents": [
                "explore", "figma-analyzer", "figma-asset-extractor",
                "figma-xml-developer", "orchestrator", "verifier",
            ],
            "rules": ["figma", "xml", "lean"],
        },
        "android": {
            "skills": [
                "agp-9-upgrade", "android-code-indexer", "android-intent-security",
                "android-profiler", "android-xml-views", "appfunctions", "code-review",
                "document_project", "gradle-run", "image-loading-glide",
                "kotlin-api-design", "kotlin-concurrency-and-flow",
                "kotlin-control-flow", "lean", "lean-audit", "lean-debt", "lean-gain",
                "lean-help", "lean-review", "loop", "play-policy-insights",
                "r8-analyzer", "mobilerun", "shape-view", "testing-setup",
                "translate-strings", "ultrawork", "xml-resource-policy",
                "xxpermissions-ktx",
            ],
            "agents": ["explore", "oracle", "orchestrator", "executor", "verifier"],
            "rules": ["xml", "lean"],
        },
    },
}


# --------------------------------------------------------------------------
# source inspection
# --------------------------------------------------------------------------

def die(msg: str) -> None:
    print(f"aha: {msg}", file=sys.stderr)
    sys.exit(1)


def select_track(track: str) -> None:
    """Point the installer at one of the two payload trees."""
    global SOURCE_ROOT, SOURCE_AGENTS
    if track not in TRACKS:
        die(f"unknown track {track!r} (have: {', '.join(TRACKS)})")
    SOURCE_ROOT = ASSETS_ROOT / track
    SOURCE_AGENTS = SOURCE_ROOT / ".agents"
    if not SOURCE_AGENTS.is_dir():
        die(f"no {SOURCE_AGENTS} -- run this from the harness repo")


def select_platform(platform: str) -> None:
    """Point the installer at one agent host: Antigravity or Claude Code."""
    global PLATFORM, HARNESS_DIR, ROOT_DOC, ROOT_DOC_KEY
    if platform not in PLATFORMS:
        die(f"unknown platform {platform!r} (have: {', '.join(PLATFORMS)})")
    PLATFORM = platform
    HARNESS_DIR, ROOT_DOC = PLATFORM_LAYOUT[platform]
    ROOT_DOC_KEY = "../" + ROOT_DOC


def detect_platform(target: Path, given: str | None) -> str:
    """The platform a flag-less update/status/undo acts on: whichever is installed."""
    if given:
        return given
    installed = [p for p, (d, _) in PLATFORM_LAYOUT.items()
                 if (target / d / MANIFEST_NAME).is_file() or (target / d / LEGACY_MANIFEST_NAME).is_file()]
    if len(installed) > 1:
        die(f"both {' and '.join(installed)} harnesses are installed -- pass --platform")
    return installed[0] if installed else DEFAULT_PLATFORM


def source_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def is_excluded(rel: str) -> bool:
    rel = rel.replace(os.sep, "/")
    for pat in EXCLUDES:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch("**/" + rel, pat):
            return True
    return any(part == "__pycache__" for part in rel.split("/"))


def components(kind: str) -> list[str]:
    """Names available under .agents/<kind>/ (dir name, or filename sans .md)."""
    root = SOURCE_AGENTS / kind
    if not root.is_dir():
        return []
    names = []
    for entry in sorted(root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            names.append(entry.name)
        elif entry.suffix == ".md":
            names.append(entry.stem)
    return names


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# rendering: the bytes a file installs as on the selected platform
# --------------------------------------------------------------------------

def source_path(rel: str) -> Path:
    if PLATFORM == "claude" and (CLAUDE_OVERLAY / rel).is_file():
        return CLAUDE_OVERLAY / rel
    return SOURCE_AGENTS / rel


def claude_text(text: str, prose: bool) -> str:
    """Repoint `.agents/` at `.claude/`; in prose, also rename Antigravity tools."""
    text = AGENTS_PATH_RE.sub(".claude", text)
    if prose:
        text = CLAUDE_PROSE_RE.sub(lambda m: CLAUDE_PROSE[m.group(1)], text)
    return text


def claude_agent(text: str, name: str) -> str:
    """Rewrite an Antigravity agent's frontmatter into a Claude Code subagent's."""
    m = re.match(r"---\r?\n(.*?)\r?\n---(\r?\n)", text, re.S)
    if not m:
        return claude_text(text, prose=True)
    nl = m.group(2)
    main_agent = re.search(r"^mainAgent:\s*true\s*$", m.group(1), re.M) is not None
    kept, tools, key = [], [], None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_][\w-]*):(.*)$", line)
        if km:
            key, value = km.group(1), km.group(2).strip()
            if key == "tools":
                tools += [t.strip() for t in value.split(",") if t.strip()]
            if key == "description" and main_agent:
                # A Claude subagent cannot dispatch subagents, so the planner has
                # to be the session itself -- say so where the router reads it.
                line = (f"description: \"Main-session planner: start it with `claude --agent {name}`. "
                        "Never dispatch it as a subagent -- it only plans and delegates, "
                        "and a subagent cannot delegate.\"")
            if key in ("tools", "model", "subagent", "mainAgent"):
                continue
        elif key == "tools":
            if line.strip().startswith("-"):
                tools.append(line.strip()[1:].strip())
            continue
        elif key in ("model", "subagent", "mainAgent") or (key == "description" and main_agent):
            continue
        kept.append(line)
    kept.append(f"model: {CLAUDE_AGENT_MODELS.get(name, SUBAGENT_MODEL)}")
    # Agents driving MCP servers (figma-*, verifier) inherit all tools in Claude Code
    # rather than having an explicit list shut MCP tools out.
    if tools and not (name.startswith("figma-") or name == "verifier"):
        mapped = list(dict.fromkeys(CLAUDE_TOOLS.get(t, t) for t in tools))
        if "Grep" in mapped and "Glob" not in mapped:
            mapped.insert(mapped.index("Grep") + 1, "Glob")
        kept.append("tools: " + ", ".join(mapped))
    head = "---" + nl + nl.join(kept) + nl + "---" + nl
    return head + claude_text(text[m.end():], prose=True)


def render(rel: str) -> bytes:
    src = source_path(rel)
    data = src.read_bytes()
    if rel == "agents/verifier.md":
        try:
            text = data.decode("utf-8")
            text = update_verifier_mode_in_text(text, VERIFIER_MODE)
            data = text.encode("utf-8")
        except UnicodeDecodeError:
            pass
    if rel == "mcp_config.json":
        wanted = wanted_mcp(MOBILERUN_ON)
        servers = {n: spec for n, spec in source_mcp_servers().items() if n in wanted}
        data = (json.dumps({"mcpServers": servers}, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if PLATFORM != "claude" or src.suffix not in TEXT_SUFFIXES:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    parts = rel.split("/")
    if parts[0] == "agents" and len(parts) == 2 and rel.endswith(".md"):
        text = claude_agent(text, parts[1][:-3])
    else:
        text = claude_text(text, prose=src.suffix == ".md")
    return text.encode("utf-8")


def render_digest(rel: str) -> str:
    return hashlib.sha256(render(rel)).hexdigest()


# --------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------

def resolve_selection(args) -> dict[str, set[str] | None]:
    """Map each component kind to the set of names to install, or None = all."""
    track_profiles = PROFILES[args.track]
    profile = track_profiles.get(args.profile) if args.profile != "full" else None
    if args.profile != "full" and profile is None:
        die(f"unknown profile {args.profile!r} for track {args.track!r} "
            f"(have: full, {', '.join(track_profiles)})")

    selection: dict[str, set[str] | None] = {}
    for kind in ("skills", "agents", "rules"):
        if getattr(args, "no_" + kind, False):
            selection[kind] = set()
            continue
        override = getattr(args, kind, None)
        if override:
            wanted = {n.strip() for n in override.split(",") if n.strip()}
            available = set(components(kind))
            missing = sorted(wanted - available)
            if missing:
                die(f"no such {kind}: {', '.join(missing)}")
            selection[kind] = wanted
        elif profile is not None:
            selection[kind] = set(profile.get(kind, []))
        else:
            selection[kind] = None
    return selection


def selected(rel: str, selection: dict) -> bool:
    """Does this path, relative to .agents/, survive the selection filter?"""
    parts = rel.replace(os.sep, "/").split("/")
    kind = parts[0]
    if kind not in selection or selection[kind] is None:
        return True
    if len(parts) < 2:
        return True
    name = parts[1][:-3] if parts[1].endswith(".md") and len(parts) == 2 else parts[1]
    return name in selection[kind]


def plan_files(selection: dict, include_hooks: bool, include_mcp: bool) -> list[str]:
    files = []
    for dirpath, dirnames, filenames in os.walk(SOURCE_AGENTS):
        dirnames[:] = [d for d in dirnames if not is_excluded(
            os.path.relpath(os.path.join(dirpath, d), SOURCE_AGENTS))]
        for fn in filenames:
            abs_path = Path(dirpath) / fn
            rel = os.path.relpath(abs_path, SOURCE_AGENTS).replace(os.sep, "/")
            if is_excluded(rel):
                continue
            if rel == "hooks.json" and not include_hooks:
                continue
            if rel.startswith("hooks/") and not include_hooks:
                continue
            if rel == "mcp_config.json" and not include_mcp:
                continue
            if not selected(rel, selection):
                continue
            if PLATFORM == "claude" and rel in MERGEABLE:
                continue  # wired into settings.json / .mcp.json, not copied
            files.append(rel)
    if PLATFORM == "claude" and include_hooks:
        files.append(CLAUDE_ADAPTER)
    return sorted(files)


# --------------------------------------------------------------------------
# merging
# --------------------------------------------------------------------------

def merge_json(src: Path, dst: Path, key: str | None) -> str:
    """Merge src into an existing dst. Existing keys in dst win. Returns text."""
    try:
        target = json.loads(dst.read_text(encoding="utf-8"))
        incoming = json.loads(src.read_text(encoding="utf-8"))
    except Exception:
        return src.read_text(encoding="utf-8")
    if key:
        merged = dict(incoming.get(key, {}))
        merged.update(target.get(key, {}))
        out = dict(target)
        out[key] = merged
    else:
        out = dict(incoming)
        out.update(target)
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def splice_block(existing: str, block: str) -> str:
    """Put `block` into `existing`, replacing a previous block if one is there."""
    start = existing.find(BLOCK_START)
    end = existing.find(BLOCK_END)
    end_tag_len = len(BLOCK_END)
    if start == -1 or end <= start:
        start = existing.find(LEGACY_BLOCK_START)
        end = existing.find(LEGACY_BLOCK_END)
        end_tag_len = len(LEGACY_BLOCK_END)
    if start != -1 and end > start:
        tail = existing[end + end_tag_len:]
        return existing[:start] + block.strip() + tail
    if not existing.strip():
        return block
    return existing.rstrip() + "\n\n" + block


def extract_block(text: str) -> str:
    """The block as it currently sits in a file, or "" if it is not there."""
    start = text.find(BLOCK_START)
    end = text.find(BLOCK_END)
    end_tag_len = len(BLOCK_END)
    if start == -1 or end <= start:
        start = text.find(LEGACY_BLOCK_START)
        end = text.find(LEGACY_BLOCK_END)
        end_tag_len = len(LEGACY_BLOCK_END)
    if start == -1 or end <= start:
        return ""
    return text[start:end + end_tag_len].strip()


def source_block() -> str:
    # Both platforms splice the one delegation rule; Claude's copy is rendered from it.
    src = SOURCE_ROOT / PLATFORM_LAYOUT[DEFAULT_PLATFORM][1]
    if not src.is_file():
        return ""
    text = src.read_text(encoding="utf-8").strip()
    if PLATFORM != "claude":
        return text
    text = text.replace("\r\n", "\n")
    for old, new in CLAUDE_ROOT_DOC_EDITS:
        text = text.replace(old, new)
    text = claude_text(text, prose=True)
    models = (f"Subagents run on `{SUBAGENT_MODEL}`; "
              + " and ".join(f"`{n}`" for n in CLAUDE_AGENT_MODELS) + " run on `opus` "
              "(start the session with `claude --agent orchestrator` to plan on it).")
    return text.replace(BLOCK_END, models + "\n" + BLOCK_END)


def write_root_doc(target: Path, dry_run: bool) -> tuple[str, str | None]:
    """Install AGENTS.md at the target root. Returns (what happened, digest)."""
    block = source_block()
    if not block:
        return "missing", None
    dst = target / ROOT_DOC
    existing = dst.read_text(encoding="utf-8") if dst.is_file() else ""
    text = splice_block(existing, block + "\n")
    if not text.endswith("\n"):
        text += "\n"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    if existing == text:
        return "current", digest
    if not dry_run:
        # newline="\n" on purpose: the digest above is of these exact bytes, and
        # text mode would silently write CRLF on Windows and never match again.
        with dst.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    if not existing:
        return "created", digest
    return "updated" if (BLOCK_START in existing or LEGACY_BLOCK_START in existing) else "appended", digest


def strip_block(existing: str) -> str:
    """Take our block back out, leaving whatever the project wrote around it."""
    start = existing.find(BLOCK_START)
    end = existing.find(BLOCK_END)
    end_tag_len = len(BLOCK_END)
    if start == -1 or end <= start:
        start = existing.find(LEGACY_BLOCK_START)
        end = existing.find(LEGACY_BLOCK_END)
        end_tag_len = len(LEGACY_BLOCK_END)
    if start == -1 or end <= start:
        return existing
    head = existing[:start].rstrip()
    tail = existing[end + end_tag_len:].lstrip()
    if head and tail:
        return head + "\n\n" + tail
    return (head + tail).strip()


def git_exclude_file(target: Path) -> Path | None:
    """Resolve <target>/.git/info/exclude via git rev-parse or fallback."""
    try:
        out = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--git-path", "info/exclude"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            p = Path(out.stdout.strip())
            return p if p.is_absolute() else (target / p).resolve()
    except Exception:
        pass
    fallback = target / ".git" / "info" / "exclude"
    if (target / ".git").is_dir() or fallback.is_file():
        return fallback.resolve()
    return None


def git_repo_prefix(target: Path) -> str:
    """Return repository-relative prefix for target (e.g. '' at root or 'sub/')."""
    try:
        out = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--show-prefix"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return ""


def build_exclude_block(prefix: str, rel_files: list[str]) -> tuple[str, int]:
    """Build the marked block of individually excluded files for .git/info/exclude."""
    prefix_agents = f"/{prefix}.agents" if prefix else "/.agents"
    entries = set()
    for rel in rel_files:
        if rel == ROOT_DOC_KEY or rel.startswith(".."):
            continue
        entries.add(f"{prefix_agents}/{rel.replace(os.sep, '/')}")
    entries.add(f"{prefix_agents}/{MANIFEST_NAME}")
    lines = [EXCLUDE_BLOCK_START] + sorted(entries) + [EXCLUDE_BLOCK_END]
    return "\n".join(lines) + "\n", len(entries)


def splice_exclude_block(existing: str, block: str) -> str:
    """Put `block` into `existing`, replacing a previous exclude block if present."""
    start = existing.find(EXCLUDE_BLOCK_START)
    end = existing.find(EXCLUDE_BLOCK_END)
    end_tag_len = len(EXCLUDE_BLOCK_END)
    if start == -1 or end <= start:
        start = existing.find(LEGACY_EXCLUDE_BLOCK_START)
        end = existing.find(LEGACY_EXCLUDE_BLOCK_END)
        end_tag_len = len(LEGACY_EXCLUDE_BLOCK_END)
    if start != -1 and end > start:
        tail = existing[end + end_tag_len:].lstrip("\r\n")
        head = existing[:start].rstrip()
        if head and tail:
            return head + "\n\n" + block.strip() + "\n\n" + tail
        if head:
            return head + "\n\n" + block.strip() + "\n"
        if tail:
            return block.strip() + "\n\n" + tail
        return block.strip() + "\n"
    if not existing.strip():
        return block.strip() + "\n"
    return existing.rstrip() + "\n\n" + block.strip() + "\n"


def strip_exclude_block(existing: str) -> str:
    """Remove our exclude block, leaving whatever else was in .git/info/exclude."""
    current = existing
    while True:
        start = current.find(EXCLUDE_BLOCK_START)
        end = current.find(EXCLUDE_BLOCK_END)
        end_tag_len = len(EXCLUDE_BLOCK_END)
        if start == -1 or end <= start:
            start = current.find(LEGACY_EXCLUDE_BLOCK_START)
            end = current.find(LEGACY_EXCLUDE_BLOCK_END)
            end_tag_len = len(LEGACY_EXCLUDE_BLOCK_END)
        if start == -1 or end <= start:
            break
        head = current[:start].rstrip()
        tail = current[end + end_tag_len:].lstrip("\r\n")
        if head and tail:
            current = head + "\n\n" + tail
        elif head:
            current = head + "\n"
        else:
            current = tail
    return current


def merged_text(rel: str, src: Path, dst: Path, ours: list[str] | None = None) -> str:
    if rel == "mcp_config.json":
        current = load_json(dst)
        if current is None:
            return render(rel).decode("utf-8")
        servers, _ = sync_mcp_servers(current.get("mcpServers", {}), wanted_mcp(MOBILERUN_ON), ours or [])
        return json.dumps({**current, "mcpServers": servers}, indent=2, ensure_ascii=False) + "\n"
    if rel == "hooks.json":
        return merge_json(src, dst, None)
    return src.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# MCP servers
# --------------------------------------------------------------------------

def source_mcp_servers() -> dict:
    return (load_json(SOURCE_AGENTS / "mcp_config.json") or {}).get("mcpServers", {})


def optional_mcp_servers() -> list[str]:
    """Source servers `--mcp` and `aha mcp` choose between; mobilerun follows the verifier."""
    return [n for n in source_mcp_servers() if n != MOBILERUN]


def mcp_short(name: str) -> str:
    return {full: short for short, full in MCP_ALIASES.items()}.get(name, name)


def resolve_mcp_names(names: list[str]) -> list[str]:
    available = optional_mcp_servers()
    resolved = []
    for raw in names:
        name = MCP_ALIASES.get(raw.strip().lower(), raw.strip())
        if name == MOBILERUN:
            die("mobilerun follows the verifier mode: `aha verifier full` turns it on for this "
                "worktree, any other mode turns it off")
        if name not in available:
            die(f"no such MCP server: {raw} (have: {', '.join(mcp_short(n) for n in available)})")
        resolved.append(name)
    return [n for n in available if n in resolved]


def default_mcp(selection: dict) -> list[str]:
    """The optional servers something in this install actually uses."""
    agents = selection.get("agents")
    agents = components("agents") if agents is None else agents
    return [n for n in optional_mcp_servers()
            if n != MCP_ALIASES["figma"] or any(a.startswith("figma-") for a in agents)]


def resolve_mcp(args, manifest: dict | None, selection: dict, updating: bool) -> list[str]:
    if args.no_mcp:
        return []
    if args.mcp is not None:
        names = [n.strip() for n in args.mcp.split(",") if n.strip()]
        return [] if names in ([], ["none"]) else resolve_mcp_names(names)
    if updating and manifest:
        if "mcp_servers" in manifest:
            return [n for n in manifest["mcp_servers"] if n in optional_mcp_servers()]
        return optional_mcp_servers()  # installs from before the toggle shipped them all
    return default_mcp(selection)


def wanted_mcp(mobilerun: bool) -> list[str]:
    """Every harness server the config should hold, mobilerun included when asked."""
    optional = optional_mcp_servers() if MCP_SERVERS is None else MCP_SERVERS
    return [n for n in source_mcp_servers() if n in optional or (n == MOBILERUN and mobilerun)]


def effective_verifier_mode(target_agents: Path, default: str) -> str:
    return read_local_state(target_agents, LOCAL_VERIFIER_MODE) or default


def sync_mcp_servers(servers: dict, wanted: list[str], ours: list[str]) -> tuple[dict, dict[str, list[str]]]:
    """`servers` with the harness's entries brought in line with `wanted`.

    A wanted server missing from the config is added; one already there is refreshed
    only when it is in `ours`, and an unwanted one is removed only when it is in
    `ours` -- a same-named entry the project wrote itself is never touched.
    """
    out = dict(servers)
    changes: dict[str, list[str]] = {"added": [], "refreshed": [], "removed": []}
    for name, spec in source_mcp_servers().items():
        if name in wanted:
            if name not in out:
                out[name] = spec
                changes["added"].append(name)
            elif name in ours and out[name] != spec:
                out[name] = spec
                changes["refreshed"].append(name)
        elif name in out and name in ours:
            del out[name]
            changes["removed"].append(name)
    return out, changes


def describe_mcp_changes(changes: dict[str, list[str]], where: str) -> str:
    notes = [f"{verb} {', '.join(mcp_short(n) for n in names)}"
             for verb, names in changes.items() if names]
    return f"{'; '.join(notes)} in {where}" if notes else f"{where} already current"


def sync_agy_mcp_config(target_agents: Path, manifest: dict, mobilerun: bool) -> str:
    """Antigravity: edit the installed (untracked, per-worktree) mcp_config.json in place."""
    rel = "mcp_config.json"
    path = target_agents / rel
    if rel not in manifest.get("files", {}) and not path.is_file():
        return f"{rel} not installed (--no-mcp)"
    current = load_json(path)
    if current is None:
        return f"skipped {rel} (not valid JSON)"
    servers, changes = sync_mcp_servers(current.get("mcpServers", {}), wanted_mcp(mobilerun),
                                        list(source_mcp_servers()))
    if any(changes.values()):
        write_json(path, {**current, "mcpServers": servers})
    manifest.setdefault("files", {})[rel] = sha256(path)
    return describe_mcp_changes(changes, rel)


def set_claude_mobilerun(target: Path, target_agents: Path, on: bool) -> str:
    """Claude: .mcp.json is committed, so each worktree enables or rejects mobilerun in
    its own git-ignored settings.local.json (enabledMcpjsonServers / disabledMcpjsonServers)."""
    path = target_agents / CLAUDE_LOCAL_SETTINGS
    current = load_json(path)
    if current is None:
        return f"skipped {CLAUDE_LOCAL_SETTINGS} (not valid JSON)"
    lists = {key: [n for n in current.get(key, []) if n != MOBILERUN]
             for key in ("enabledMcpjsonServers", "disabledMcpjsonServers")}
    lists["enabledMcpjsonServers" if on else "disabledMcpjsonServers"].append(MOBILERUN)
    updated = {k: v for k, v in current.items() if k not in lists}
    updated.update({k: v for k, v in lists.items() if v})
    state = "on" if on else "off"
    if updated == current:
        return f"mobilerun already {state} in {CLAUDE_LOCAL_SETTINGS}"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, updated)
    ensure_git_ignored(target, f"{HARNESS_DIR}/{CLAUDE_LOCAL_SETTINGS}")
    return f"mobilerun {state} in {CLAUDE_LOCAL_SETTINGS} (this worktree)"


def unset_claude_mobilerun(target_agents: Path, dry_run: bool) -> str | None:
    path = target_agents / CLAUDE_LOCAL_SETTINGS
    current = load_json(path)
    if not current:
        return None
    updated = dict(current)
    for key in ("enabledMcpjsonServers", "disabledMcpjsonServers"):
        kept = [n for n in current.get(key, []) if n != MOBILERUN]
        if kept:
            updated[key] = kept
        else:
            updated.pop(key, None)
    if updated == current:
        return None
    if not dry_run:
        path.unlink() if not updated else write_json(path, updated)
    return f"removed mobilerun from {path}"


def ensure_git_ignored(target: Path, rel: str) -> None:
    """Add `rel` to .git/info/exclude unless git already ignores it."""
    try:
        if subprocess.run(["git", "-C", str(target), "check-ignore", "-q", rel],
                          capture_output=True, timeout=10).returncode == 0:
            return
    except Exception:
        return
    exclude = git_exclude_file(target)
    if not exclude:
        return
    line = git_repo_prefix(target) + rel
    existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    if line in existing.splitlines():
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(("" if not existing or existing.endswith("\n") else "\n") + line + "\n")


def mcp_summary(optional: list[str] | None, mobilerun: bool) -> str:
    enabled = optional_mcp_servers() if optional is None else optional
    parts = []
    for name in source_mcp_servers():
        if name == MOBILERUN:
            parts.append(f"mobilerun {'on' if mobilerun else 'off'} (follows verifier full)")
        else:
            parts.append(f"{mcp_short(name)} {'on' if name in enabled else 'off'}")
    return ", ".join(parts)


def apply_mobilerun(target: Path, target_agents: Path, manifest: dict) -> str:
    """Point mobilerun at this worktree's verifier mode: on for `full`, off otherwise."""
    global MCP_SERVERS
    MCP_SERVERS = manifest.get("mcp_servers")
    on =effective_verifier_mode(target_agents, manifest.get("verifier_mode", DEFAULT_VERIFIER_MODE)) == "full"
    if PLATFORM == "claude":
        return set_claude_mobilerun(target, target_agents, on)
    return sync_agy_mcp_config(target_agents, manifest, on)


# --------------------------------------------------------------------------
# Claude Code: settings.json hooks and .mcp.json
# --------------------------------------------------------------------------

def claude_hooks() -> dict:
    """hooks.json, re-expressed as Claude Code settings hooks routed via the adapter."""
    try:
        groups = json.loads((SOURCE_AGENTS / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    adapter = f'"$CLAUDE_PROJECT_DIR/.claude/{CLAUDE_ADAPTER}"'

    def command(*args: str) -> str:
        # macOS has no bare `python`; Windows' `python3` is often the Store stub. The
        # adapter always exits 0, so the fallback only fires when python3 is absent.
        line = " ".join([adapter, *args])
        return f"python3 {line} || python {line}"

    out: dict[str, list] = {"SessionStart": [
        {"hooks": [{"type": "command", "command": command("SessionStart"), "timeout": 10}]}]}

    def add(event: str, matcher: str | None, script: list[str], timeout) -> None:
        entry = {"hooks": [{"type": "command", "timeout": timeout,
                            "command": command(event, *script)}]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        out.setdefault(event, []).append(entry)

    for cfg in groups.values():
        if not isinstance(cfg, dict) or not cfg.get("enabled"):
            continue
        for agy_event, event in CLAUDE_EVENTS.items():
            for item in cfg.get(agy_event, []):
                for hook in item.get("hooks", [item]):
                    # `python3 X || python X`: keep the first alternative, drop the interpreter
                    words = hook.get("command", "").split("||")[0].split()[1:]
                    if not words:
                        continue
                    script = [Path(words[0]).name, *words[1:]]
                    matcher = None
                    if item.get("matcher"):
                        names = [CLAUDE_TOOLS.get(n, n) for n in item["matcher"].split("|")]
                        if "Edit" in names:
                            names.append("MultiEdit")
                        matcher = "|".join(dict.fromkeys(names))
                    add(event, matcher, script, hook.get("timeout", 10))
                    # Refcounted device owners release on their own stop; a subagent
                    # finishing is Claude's SubagentStop, not Stop.
                    if agy_event == "Stop" and script[-1] == "stop":
                        add("SubagentStop", None, script, hook.get("timeout", 10))
    return out


def strip_claude_hooks(settings: dict) -> dict:
    """Settings with every adapter-routed hook removed, and emptied containers dropped."""
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return dict(settings)
    kept_events = {}
    for event, entries in hooks.items():
        kept = []
        for entry in entries if isinstance(entries, list) else []:
            inner = [h for h in entry.get("hooks", []) if CLAUDE_ADAPTER not in str(h.get("command", ""))]
            if inner:
                kept.append({**entry, "hooks": inner})
        if kept:
            kept_events[event] = kept
    out = {k: v for k, v in settings.items() if k != "hooks"}
    if kept_events:
        out["hooks"] = kept_events
    return out


def load_json(path: Path) -> dict | None:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def wire_claude_settings(target_agents: Path, include_hooks: bool, dry_run: bool) -> str:
    """Replace our hooks in .claude/settings.json, leaving the project's own intact."""
    path = target_agents / CLAUDE_SETTINGS
    current = load_json(path)
    if current is None:
        return f"skipped {CLAUDE_SETTINGS} (not valid JSON -- fix it and re-run `update`)"
    settings = strip_claude_hooks(current)
    if include_hooks:
        hooks = settings.setdefault("hooks", {})
        for event, entries in claude_hooks().items():
            hooks.setdefault(event, []).extend(entries)
    if settings == current:
        return f"{CLAUDE_SETTINGS} hooks already current"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, settings)
    return f"wired hooks into {CLAUDE_SETTINGS}"


def merge_claude_mcp(target: Path, previously_added: list[str], wanted: list[str],
                     dry_run: bool) -> tuple[str, list[str]]:
    """Bring our servers in .mcp.json in line with `wanted`. The project's own entries win."""
    path = target / CLAUDE_MCP
    current = load_json(path)
    if current is None:
        return f"skipped {CLAUDE_MCP} (not valid JSON)", previously_added
    servers, changes = sync_mcp_servers(current.get("mcpServers", {}), wanted, previously_added)
    ours = sorted(n for n in servers if n in wanted and (n in previously_added or n in changes["added"]))
    if not any(changes.values()):
        return describe_mcp_changes(changes, CLAUDE_MCP), ours
    if not dry_run:
        rest = {k: v for k, v in current.items() if k != "mcpServers"}
        if servers:
            rest["mcpServers"] = servers
        path.unlink(missing_ok=True) if not rest else write_json(path, rest)
    return describe_mcp_changes(changes, CLAUDE_MCP), ours


def unmerge_claude(target: Path, target_agents: Path, mcp_added: list[str], dry_run: bool) -> list[str]:
    """Take our hooks and MCP servers back out; delete a file only if nothing else is left."""
    notes = []
    path = target_agents / CLAUDE_SETTINGS
    current = load_json(path)
    if current:
        stripped = strip_claude_hooks(current)
        if stripped != current:
            notes.append(f"removed harness hooks from {path}")
            if not dry_run:
                path.unlink() if not stripped else write_json(path, stripped)
    path = target / CLAUDE_MCP
    current = load_json(path)
    if current and mcp_added:
        servers = {k: v for k, v in current.get("mcpServers", {}).items() if k not in mcp_added}
        rest = {k: v for k, v in current.items() if k != "mcpServers"}
        if servers:
            rest["mcpServers"] = servers
        if rest != current:
            notes.append(f"removed {', '.join(mcp_added)} from {path}")
            if not dry_run:
                path.unlink() if not rest else write_json(path, rest)
    return notes


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def read_manifest(target_agents: Path) -> dict | None:
    path = target_agents / MANIFEST_NAME
    if not path.is_file():
        path = target_agents / LEGACY_MANIFEST_NAME
        if not path.is_file():
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_manifest(target_agents: Path, files: dict[str, str], args,
                   extra: dict | None = None) -> None:
    manifest = {
        "source": str(SOURCE_ROOT),
        "commit": source_commit(),
        "platform": PLATFORM,
        "track": args.track,
        "profile": args.profile,
        "verifier_mode": VERIFIER_MODE,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        **(extra or {}),
        "files": files,
    }
    (target_agents / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def classify(target_agents: Path, manifest: dict | None) -> dict[str, list[str]]:
    """Split installed files into unchanged / modified-locally / deleted."""
    result = {"unchanged": [], "modified": [], "deleted": []}
    if not manifest:
        return result
    for rel, digest in sorted(manifest.get("files", {}).items()):
        path = target_agents / rel
        if not path.is_file():
            result["deleted"].append(rel)
        elif sha256(path) == digest:
            result["unchanged"].append(rel)
        else:
            result["modified"].append(rel)
    return result


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def prune_empty_dirs(root: Path) -> None:
    """Remove directories left empty by a prune. Never removes `root` itself."""
    dirs = [d for d, _, _ in os.walk(root)]
    for dirpath in sorted(dirs, key=len, reverse=True):
        path = Path(dirpath)
        if path == root:
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()
        except OSError:
            pass


def do_install(args, updating: bool) -> int:
    target = Path(args.target).resolve()
    if not target.is_dir():
        die(f"target {target} is not a directory")
    target_agents = target / HARNESS_DIR
    if target_agents.resolve() == SOURCE_AGENTS.resolve():
        die("target is the harness source itself")
    if target == REPO_ROOT:
        die("the harness repo keeps no .agents/ of its own -- edit assets/ instead")

    manifest = read_manifest(target_agents)
    # A project's .claude/ usually predates us (settings.local.json), so for Claude
    # only an existing install blocks init; clashing files are kept, below.
    existing = bool(manifest) if PLATFORM == "claude" else target_agents.exists()

    if existing and not updating and not args.force:
        die(f"{target_agents} already exists -- use `update`, or `init --force`")

    state = classify(target_agents, manifest)
    protected = set(state["modified"]) if (updating and not args.overwrite_local) else set()

    global VERIFIER_MODE
    if hasattr(args, "verifier_mode") and args.verifier_mode:
        VERIFIER_MODE = args.verifier_mode
    elif updating and manifest and "verifier_mode" in manifest:
        VERIFIER_MODE = manifest["verifier_mode"]
    else:
        VERIFIER_MODE = DEFAULT_VERIFIER_MODE

    global MCP_SERVERS, MOBILERUN_ON
    selection = resolve_selection(args)
    MCP_SERVERS = resolve_mcp(args, manifest, selection, updating)
    # A worktree override can raise this worktree's verifier, and mobilerun with it.
    MOBILERUN_ON = not args.no_mcp and effective_verifier_mode(target_agents, VERIFIER_MODE) == "full"
    files = plan_files(selection, include_hooks=not args.no_hooks,
                       include_mcp=not args.no_mcp)
    if not files:
        die("selection is empty -- nothing to install")

    written, skipped, merged, theirs, unchanged_n = [], [], [], [], 0
    digests: dict[str, str] = {}

    for rel in files:
        src = SOURCE_AGENTS / rel
        dst = target_agents / rel
        data = render(rel)
        want = hashlib.sha256(data).hexdigest()
        if rel in protected:
            skipped.append(rel)
            digests[rel] = manifest["files"][rel] if manifest else want
            continue
        if (PLATFORM == "claude" and manifest is None and not args.force
                and dst.is_file() and sha256(dst) != want):
            theirs.append(rel)  # the project's own file, never recorded as ours
            continue

        text = None
        if rel in MERGEABLE and dst.is_file() and manifest is None:
            text = merged_text(rel, src, dst)
            merged.append(rel)
        elif rel == "mcp_config.json" and dst.is_file():
            # Ours since install: keep the project's servers, bring ours in line.
            text = merged_text(rel, src, dst, ours=list(source_mcp_servers()))

        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if text is None:
                if dst.is_file() and sha256(dst) == want:
                    unchanged_n += 1
                    digests[rel] = want
                    continue
                dst.write_bytes(data)
                shutil.copymode(source_path(rel), dst)
            else:
                dst.write_text(text, encoding="utf-8")
            digests[rel] = sha256(dst)
        else:
            digests[rel] = want
        written.append(rel)

    root_doc = None
    if not args.no_agents_md:
        root_doc, root_digest = write_root_doc(target, args.dry_run)
        if root_digest:
            digests[ROOT_DOC_KEY] = root_digest

    # Files this install no longer ships but a previous one did. AGENTS.md is
    # never in here: it is not ours to delete, only our block inside it is, and
    # `remove` is the command that takes that block back.
    stale = []
    if manifest:
        shipped = set(files) | {ROOT_DOC_KEY}
        for rel in manifest.get("files", {}):
            if rel not in shipped and (target_agents / rel).is_file() and rel not in state["modified"]:
                stale.append(rel)
                if not args.dry_run and args.prune:
                    (target_agents / rel).unlink()

    if stale and args.prune and not args.dry_run:
        prune_empty_dirs(target_agents)

    claude_notes, extra = [], {"mcp_servers": MCP_SERVERS}
    if PLATFORM == "claude":
        claude_notes.append(wire_claude_settings(target_agents, not args.no_hooks, args.dry_run))
        mcp_added = (manifest or {}).get("mcp_added", [])
        if not args.no_mcp:
            # .mcp.json is committed, so it always defines mobilerun; each worktree's
            # settings.local.json switches it on or off.
            note, mcp_added = merge_claude_mcp(target, mcp_added, wanted_mcp(True), args.dry_run)
            claude_notes.append(note)
            if not args.dry_run and MOBILERUN in mcp_added:
                claude_notes.append(set_claude_mobilerun(target, target_agents, MOBILERUN_ON))
        extra.update(subagent_model=SUBAGENT_MODEL, mcp_added=mcp_added)

    if not args.dry_run:
        target_agents.mkdir(parents=True, exist_ok=True)
        write_manifest(target_agents, digests, args, extra)
        # Earlier installs pinned the serial in the manifest and MCP config; it is a
        # per-worktree preference now, carried over once.
        device = getattr(args, "device_serial", None) or (manifest or {}).get("device_serial")
        if device and (args.device_serial or not read_local_state(target_agents, LOCAL_DEVICE)):
            write_local_state(target_agents, LOCAL_DEVICE, device)

    exclude_status = None
    exclude_n = 0
    # A Claude install is committed with the project, so it is never git-excluded.
    if not args.no_git_exclude and PLATFORM != "claude":
        exclude_path = git_exclude_file(target)
        if exclude_path:
            prefix = git_repo_prefix(target)
            all_exclude = set(files)
            if manifest:
                for rel in manifest.get("files", {}):
                    if rel != ROOT_DOC_KEY and not rel.startswith("..") and (target_agents / rel).is_file():
                        all_exclude.add(rel)
            block, exclude_n = build_exclude_block(prefix, sorted(all_exclude))
            existing_ex = exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else ""
            new_ex = splice_exclude_block(existing_ex, block)
            if existing_ex == new_ex:
                exclude_status = "current"
            else:
                exclude_status = "would update" if args.dry_run else "updated"
                if not args.dry_run:
                    exclude_path.parent.mkdir(parents=True, exist_ok=True)
                    with exclude_path.open("w", encoding="utf-8", newline="\n") as fh:
                        fh.write(new_ex)

    verb = "would write" if args.dry_run else "wrote"
    print(f"aha {'update' if updating else 'init'} -> {target_agents}")
    print(f"  platform     {PLATFORM}")
    print(f"  track        {args.track}")
    print(f"  profile      {args.profile}  (source {source_commit()})")
    local_mode = read_local_state(target_agents, LOCAL_VERIFIER_MODE)
    local_device = read_local_state(target_agents, LOCAL_DEVICE)
    print(f"  verifier     {VERIFIER_MODE}"
          + (f"  (this worktree: {local_mode})" if local_mode else ""))
    if local_device:
        print(f"  device       prefers {local_device} when free (this worktree only)")
    if not args.no_mcp:
        print(f"  mcp          {mcp_summary(MCP_SERVERS, MOBILERUN_ON)}")
    print(f"  {verb:<12} {len(written)} file(s)"
          + (f", {unchanged_n} already current" if unchanged_n else ""))
    if root_doc == "created":
        print(f"  {verb:<12} {ROOT_DOC} (delegation rule, project root)")
    elif root_doc == "appended":
        print(f"  appended     {ROOT_DOC} (your content kept; ours is the marked block)")
    elif root_doc == "updated":
        print(f"  refreshed    {ROOT_DOC} (marked block only; the rest is untouched)")
    elif root_doc == "current":
        print(f"  {ROOT_DOC:<12} already current")
    if exclude_status:
        if exclude_status == "current":
            print("  git exclude  .git/info/exclude already current")
        else:
            print(f"  git exclude  {exclude_status} .git/info/exclude ({exclude_n} entries)")
    for rel in merged:
        print(f"  merged       {rel} (your entries kept, harness entries added)")
    for note in claude_notes:
        print(f"  settings     {note}")
    for rel in theirs:
        print(f"  kept yours   {rel} (already in the project; --force to replace)")
    for rel in skipped:
        print(f"  kept local   {rel} (edited since install; --overwrite-local to replace)")
    for rel in stale:
        print(f"  {'pruned' if args.prune and not args.dry_run else 'orphaned'}       {rel}"
              + ("" if args.prune else " (no longer in profile; --prune to delete)"))
    if not existing and not args.dry_run and PLATFORM == "claude":
        print("\nNext: open the project in Claude Code. `CLAUDE.md` and `.claude/rules/*.md`")
        print(f"load always; subagents run on {SUBAGENT_MODEL}, orchestrator and oracle on opus")
        print("(`claude --agent orchestrator` plans on opus). Hooks need `python3` or `python` on PATH.")
        print("Commit .claude/, CLAUDE.md and .mcp.json to share the harness with your team.")
    elif not existing and not args.dry_run:
        print("\nNext: open the project in Antigravity. `AGENTS.md` and `.agents/rules/*.md`")
        print("load always; skills load on demand; hooks run with CWD = .agents/ and need")
        print("`python3` or `python` on PATH.")
    return 0


def do_status(args) -> int:
    target = Path(args.target).resolve()
    target_agents = target / HARNESS_DIR
    if not target_agents.is_dir():
        print(f"aha: no {HARNESS_DIR}/ in {target}")
        return 1
    manifest = read_manifest(target_agents)
    print(f"aha status -> {target_agents}")
    if not manifest:
        print(f"  no manifest -- {HARNESS_DIR}/ exists but was not installed by this CLI")
        return 1

    state = classify(target_agents, manifest)
    print(f"  installed    {manifest.get('installed_at', '?')}"
          f"  platform {manifest.get('platform', DEFAULT_PLATFORM)}"
          f"  track {manifest.get('track', DEFAULT_TRACK)}"
          f"  profile {manifest.get('profile', '?')}"
          f"  verifier {manifest.get('verifier_mode', DEFAULT_VERIFIER_MODE)}"
          f"  commit {manifest.get('commit', '?')}")
    print(f"  source       {manifest.get('source', '?')}")
    for name, label in ((LOCAL_VERIFIER_MODE, "verifier mode"), (LOCAL_DEVICE, "preferred device")):
        value = read_local_state(target_agents, name)
        if value:
            print(f"  this worktree {label} {value}")
    if "mcp_servers" in manifest or PLATFORM != "claude" or manifest.get("mcp_added"):
        print(f"  mcp          {mcp_summary(manifest.get('mcp_servers'), MOBILERUN_ON)}")

    now = source_commit()
    if manifest.get("commit") not in (now, "unknown"):
        print(f"  SOURCE MOVED source is now {now} -- run `update`")

    outdated = []
    for rel, digest in manifest.get("files", {}).items():
        if rel == ROOT_DOC_KEY:
            continue
        if source_path(rel).is_file() and render_digest(rel) != digest and rel not in state["modified"]:
            outdated.append(rel)

    # AGENTS.md is compared by block, not by file digest: the project owns
    # everything outside the markers, so a whole-file diff says nothing.
    if ROOT_DOC_KEY in manifest.get("files", {}):
        root_dst = target / ROOT_DOC
        here = extract_block(root_dst.read_text(encoding="utf-8")) if root_dst.is_file() else ""
        if not here:
            print(f"  {ROOT_DOC:<12} block missing -- run `update` to restore it")
        elif here != source_block():
            print(f"  {ROOT_DOC:<12} block differs from source -- run `update`")
        else:
            print(f"  {ROOT_DOC:<12} block current")
    if PLATFORM == "claude":
        settings = load_json(target_agents / CLAUDE_SETTINGS) or {}
        wired = strip_claude_hooks(settings) != settings
        print(f"  {CLAUDE_SETTINGS:<12} "
              + ("harness hooks wired" if wired else "no harness hooks -- run `update`"))

    print(f"  {len(state['unchanged'])} unchanged, {len(state['modified'])} edited locally,"
          f" {len(state['deleted'])} deleted, {len(outdated)} stale vs source")
    for label, items in (("edited locally", state["modified"]),
                         ("deleted", state["deleted"]),
                         ("stale vs source", outdated)):
        for rel in items[:20]:
            print(f"    {label:<16} {rel}")
        if len(items) > 20:
            print(f"    {label:<16} ... and {len(items) - 20} more")
    return 0


def do_remove(args) -> int:
    target = Path(args.target).resolve()
    target_agents = target / HARNESS_DIR
    if not target_agents.is_dir():
        die(f"no {HARNESS_DIR}/ in {target}")
    manifest = read_manifest(target_agents)
    if manifest is None and not args.force:
        die(f"{target_agents} has no aha manifest -- refusing to delete "
            "a directory this CLI did not install (use --force)")

    state = classify(target_agents, manifest)
    if state["modified"] and not args.force:
        print(f"aha: {len(state['modified'])} file(s) edited since install:")
        for rel in state["modified"][:20]:
            print(f"    {rel}")
        die("refusing to delete local edits -- re-run with --force")

    root_dst = target / ROOT_DOC
    root_action = None
    if root_dst.is_file():
        before = root_dst.read_text(encoding="utf-8")
        if BLOCK_START in before or LEGACY_BLOCK_START in before:
            rest = strip_block(before)
            root_action = "delete" if not rest else "unsplice"

    # The exclude block belongs to the Antigravity install; a Claude one never wrote it.
    exclude_path = git_exclude_file(target) if PLATFORM != "claude" else None
    exclude_action = None
    if exclude_path and exclude_path.is_file():
        ex_content = exclude_path.read_text(encoding="utf-8")
        if EXCLUDE_BLOCK_START in ex_content or LEGACY_EXCLUDE_BLOCK_START in ex_content:
            exclude_action = "strip"

    files_to_delete: list[Path] = []
    if manifest:
        for rel in manifest.get("files", {}):
            if rel == ROOT_DOC_KEY or rel.startswith(".."):
                continue
            p = target_agents / rel
            if p.is_file():
                files_to_delete.append(p)
    for m in (MANIFEST_NAME, LEGACY_MANIFEST_NAME):
        p = target_agents / m
        if p.is_file() and p not in files_to_delete:
            files_to_delete.append(p)
    local = target_agents / LOCAL_STATE_DIR
    for name in (LOCAL_VERIFIER_MODE, LOCAL_DEVICE, ".gitignore"):
        if (local / name).is_file():
            files_to_delete.append(local / name)

    claude_notes = []
    if PLATFORM == "claude":
        claude_notes = unmerge_claude(target, target_agents, (manifest or {}).get("mcp_added", []),
                                      args.dry_run)
        note = unset_claude_mobilerun(target_agents, args.dry_run)
        if note:
            claude_notes.append(note)

    all_agent_files = {p.resolve() for p in target_agents.rglob("*") if p.is_file()}
    delete_set = {p.resolve() for p in files_to_delete}
    remaining_files = all_agent_files - delete_set

    if args.dry_run:
        if remaining_files:
            print(f"aha: would delete {len(files_to_delete)} harness file(s) and preserve {target_agents} ({len(remaining_files)} non-harness file(s) remain)")
        else:
            print(f"aha: would delete {len(files_to_delete)} file(s) and remove {target_agents}")
        if exclude_action == "strip":
            print(f"aha: would remove exclude block from {exclude_path}")
        for note in claude_notes:
            print(f"aha: would have {note}")
        if root_action == "delete":
            print(f"aha: would delete {root_dst} (only our block is in it)")
        elif root_action == "unsplice":
            print(f"aha: would remove our block from {root_dst}, keeping your content")
        return 0

    for path in files_to_delete:
        try:
            path.unlink()
        except OSError:
            pass

    prune_empty_dirs(target_agents)

    has_remaining = False
    try:
        next(target_agents.iterdir())
        has_remaining = True
    except (StopIteration, OSError):
        pass

    if has_remaining:
        print(f"aha: removed {len(files_to_delete)} harness file(s); preserved {target_agents} (contains other files)")
    else:
        try:
            target_agents.rmdir()
            print(f"aha: removed {target_agents}")
        except OSError:
            print(f"aha: removed {len(files_to_delete)} harness file(s)")

    if exclude_action == "strip" and exclude_path and exclude_path.is_file():
        ex_content = exclude_path.read_text(encoding="utf-8")
        stripped = strip_exclude_block(ex_content)
        if stripped != ex_content:
            with exclude_path.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(stripped)
            print(f"aha: removed exclude block from {exclude_path}")
    for note in claude_notes:
        print(f"aha: {note}")

    if root_action == "delete":
        root_dst.unlink()
        print(f"aha: removed {root_dst}")
    elif root_action == "unsplice":
        kept = strip_block(root_dst.read_text(encoding="utf-8")) + "\n"
        with root_dst.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(kept)
        print(f"aha: removed our block from {root_dst}, kept your content")
    return 0


def do_verifier(args) -> int:
    """Get or set this worktree's verifier mode and preferred device.

    Both are per-worktree, untracked settings: the verifier reads its mode from
    state/verifier_mode before the project default in verifier.md, and the device
    lease prefers state/device when it is free. mobilerun follows the mode -- on
    for `full`, off otherwise -- through per-worktree config only, so a committed
    install stays clean in every worktree.
    """
    target = Path(args.target).resolve()
    target_agents = target / HARNESS_DIR
    manifest = read_manifest(target_agents)
    if not manifest:
        die(f"no harness found at {target} -- run 'aha init' first")
    default = manifest.get("verifier_mode", DEFAULT_VERIFIER_MODE)

    changed = []
    if args.reset:
        write_local_state(target_agents, LOCAL_VERIFIER_MODE, None)
        changed.append(f"verifier mode reset to the project default: {default}")
    elif args.mode:
        write_local_state(target_agents, LOCAL_VERIFIER_MODE, args.mode)
        changed.append(f"verifier mode set to: {args.mode} (this worktree)")
    if args.device_serial is not None:
        write_local_state(target_agents, LOCAL_DEVICE, args.device_serial or None)
        changed.append(f"preferred device: {args.device_serial} (this worktree)"
                       if args.device_serial else "preferred device cleared")
    if args.reset or args.mode:
        note = apply_mobilerun(target, target_agents, manifest)
        write_json(target_agents / MANIFEST_NAME, manifest)
        changed.append(f"{note} -- restart the agent session to load the change")
    for line in changed:
        print(line)
    if changed:
        return 0

    local = read_local_state(target_agents, LOCAL_VERIFIER_MODE)
    source = "this worktree" if local else "project default"
    print(f"verifier mode: {local or default} ({source}; target: {target})")
    device = read_local_state(target_agents, LOCAL_DEVICE)
    print(f"preferred device: {device or 'none -- any free device'}")
    print(f"mcp: {mcp_summary(manifest.get('mcp_servers'), (local or default) == 'full')}")
    return 0


def do_mcp(args) -> int:
    """Show the harness MCP servers, or switch an optional one on or off."""
    target = Path(args.target).resolve()
    target_agents = target / HARNESS_DIR
    manifest = read_manifest(target_agents)
    if not manifest:
        die(f"no harness found at {target} -- run 'aha init' first")
    mode = effective_verifier_mode(target_agents, manifest.get("verifier_mode", DEFAULT_VERIFIER_MODE))
    enabled = manifest.get("mcp_servers")
    enabled = optional_mcp_servers() if enabled is None else enabled

    if args.action is None:
        for name in source_mcp_servers():
            if name == MOBILERUN:
                print(f"  {'mobilerun':<10} {'on ' if mode == 'full' else 'off'}  "
                      f"follows the verifier (this worktree: {mode}) -- `aha verifier full|compact`")
            else:
                print(f"  {mcp_short(name):<10} {'on ' if name in enabled else 'off'}  "
                      f"`aha mcp {'off' if name in enabled else 'on'} {mcp_short(name)}`")
        return 0

    if not args.names:
        die(f"name a server to switch {args.action}: {', '.join(mcp_short(n) for n in optional_mcp_servers())}")
    names = resolve_mcp_names(args.names)
    wanted = [n for n in optional_mcp_servers()
              if (n in enabled and n not in names) or (n in names and args.action == "on")]
    manifest["mcp_servers"] = wanted
    global MCP_SERVERS
    MCP_SERVERS = wanted
    if PLATFORM == "claude":
        note, manifest["mcp_added"] = merge_claude_mcp(
            target, manifest.get("mcp_added", []), wanted_mcp(True), dry_run=False)
    else:
        note = sync_agy_mcp_config(target_agents, manifest, mode == "full")
    write_json(target_agents / MANIFEST_NAME, manifest)
    print(f"{', '.join(mcp_short(n) for n in names)} {args.action}: {note}")
    print("restart the agent session to load the change")
    return 0


def do_worktree(args) -> int:
    """`git worktree add`, then install the same harness into the new worktree."""
    source = Path(args.source).resolve()
    manifest = read_manifest(source / HARNESS_DIR)
    if not manifest:
        die(f"no harness installed at {source} -- run this from a worktree that has one")
    prefix = git_repo_prefix(source)
    proc = subprocess.run(["git", "-C", str(source), "worktree", "add", args.path, *args.git_args])
    if proc.returncode != 0:
        return proc.returncode
    worktree = Path(args.path)
    if not worktree.is_absolute():
        worktree = (Path.cwd() / worktree).resolve()
    target = worktree / prefix if prefix else worktree
    checked_out = read_manifest(target / HARNESS_DIR)
    if checked_out:
        # A committed install arrives with the checkout; only the per-worktree
        # mobilerun switch is missing.
        note = apply_mobilerun(target, target / HARNESS_DIR, checked_out)
        print(f"aha: {target / HARNESS_DIR} came with the checkout (committed install); {note}")
        return 0
    optional = manifest.get("mcp_servers")
    argv = ["init", str(target), "--platform", PLATFORM,
            "--track", manifest.get("track", DEFAULT_TRACK),
            "--profile", manifest.get("profile", "full"),
            "--verifier-mode", manifest.get("verifier_mode", DEFAULT_VERIFIER_MODE)]
    if optional is not None:
        argv += ["--mcp", ",".join(mcp_short(n) for n in optional) or "none"]
    if manifest.get("subagent_model"):
        argv += ["--subagent-model", manifest["subagent_model"]]
    return main(argv)


def do_list(args) -> int:
    print(f"aha source {SOURCE_AGENTS}  (commit {source_commit()})\n")
    for kind in ("rules", "agents", "skills"):
        names = components(kind)
        print(f"{kind} ({len(names)})")
        line = "  "
        for name in names:
            if len(line) + len(name) > 78:
                print(line)
                line = "  "
            line += name + "  "
        if line.strip():
            print(line)
        print()
    try:
        hooks = json.loads((SOURCE_AGENTS / "hooks.json").read_text(encoding="utf-8"))
        print(f"hooks ({len(hooks)})")
        for name, cfg in hooks.items():
            flag = "on " if cfg.get("enabled") else "off"
            events = [k for k in cfg if k not in ("_comment", "enabled")]
            print(f"  [{flag}] {name:<24} {', '.join(events)}")
        print()
    except Exception:
        pass
    print(f"root files ({1 if (SOURCE_ROOT / ROOT_DOC).is_file() else 0})")
    print(f"  {ROOT_DOC:<10} delegation rule, spliced into the target's root file")
    print()
    print(f"profiles (track {args.track})")
    print(f"  {'full':<10} everything above (default)")
    for name, spec in PROFILES[args.track].items():
        counts = ", ".join(f"{len(v)} {k}" for k, v in spec.items())
        print(f"  {name:<10} {counts}")
    print()
    print("verifier modes")
    print("  minimal    lint checks & diff non-negotiables only (fastest, no assemble)")
    print("  compact    Gradle assemble & unit tests (default, no device)")
    print("  full       Gradle assemble, unit tests, and mobilerun app launch")
    print()
    print("mcp servers")
    for name in source_mcp_servers():
        rule = ("on when the verifier mode is full" if name == MOBILERUN
                else "on when the figma agents ship" if name == MCP_ALIASES["figma"]
                else "on by default")
        print(f"  {mcp_short(name):<10} {rule}")
    print()
    print("tracks")
    for name in TRACKS:
        agents_dir = ASSETS_ROOT / name / ".agents"
        n = len(list((agents_dir / "skills").iterdir())) if agents_dir.is_dir() else 0
        mark = "  (shown above)" if name == args.track else ""
        print(f"  {name:<10} {n} skills{mark}")
    print(f"\n  aha list --track {TRACKS[1] if args.track == TRACKS[0] else TRACKS[0]}"
          f"   to see the other one")
    return 0


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

def add_platform_flag(p: argparse.ArgumentParser) -> None:
    p.add_argument("--platform", default=None, choices=PLATFORMS,
                   help=f"agent host: {' or '.join(PLATFORMS)} (default: {DEFAULT_PLATFORM} "
                        "on init, whichever is installed otherwise)")


def add_selection_flags(p: argparse.ArgumentParser) -> None:
    add_platform_flag(p)
    p.add_argument("--subagent-model", default=None,
                   help=f"Claude only: model for subagents (default: {DEFAULT_SUBAGENT_MODEL}; "
                        + ", ".join(CLAUDE_AGENT_MODELS) + " stay on opus)")
    p.add_argument("--verifier-mode", "--verifier", dest="verifier_mode", choices=VERIFIER_MODES, default=None,
                   help=f"verification mode: minimal (lint only), compact (gradle build), "
                        f"full (app launch with mobilerun) (default: {DEFAULT_VERIFIER_MODE})")
    p.add_argument("--device", "--device-serial", dest="device_serial", default=None,
                   help="device serial this worktree's lease prefers when it is free "
                        "(untracked, per worktree; the lease still decides)")
    p.add_argument("--track", default=None, choices=TRACKS,
                   help=f"which payload to install: {' or '.join(TRACKS)} "
                        f"(default: {DEFAULT_TRACK})")
    p.add_argument("--profile", default="full",
                   help="full (default), " + ", ".join(PROFILES[DEFAULT_TRACK]))
    p.add_argument("--skills", help="comma-separated skill names (overrides profile)")
    p.add_argument("--agents", help="comma-separated agent names (overrides profile)")
    p.add_argument("--rules", help="comma-separated rule names (overrides profile)")
    p.add_argument("--no-skills", action="store_true")
    p.add_argument("--no-agents", action="store_true")
    p.add_argument("--no-rules", action="store_true")
    p.add_argument("--no-hooks", action="store_true", help="skip hooks.json and hooks/")
    p.add_argument("--mcp", default=None,
                   help="optional MCP servers to enable, comma-separated: figma, or none "
                        "(default: figma when the figma agents ship). mobilerun is not "
                        "listed here: it is on exactly when the verifier mode is full")
    p.add_argument("--no-mcp", action="store_true", help="skip MCP config entirely")
    p.add_argument("--no-agents-md", action="store_true",
                   help=f"skip {ROOT_DOC} (leaves the project root untouched)")
    p.add_argument("--no-git-exclude", action="store_true",
                   help="skip updating .git/info/exclude (never written for claude)")
    p.add_argument("-n", "--dry-run", action="store_true", help="print the plan only")


def main(argv: list[str]) -> int:
    missing = [n for n in TRACKS if not (ASSETS_ROOT / n / ".agents").is_dir()]
    if missing:
        die(f"no assets/{missing[0]}/.agents -- run this from the harness repo")

    parser = argparse.ArgumentParser(
        prog="aha", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="copy assets/ into a project")
    p_init.add_argument("target", nargs="?", default=".",
                        help="target directory (default: .)")
    p_init.add_argument("--force", action="store_true",
                        help="proceed even if .agents/ already exists")
    p_init.add_argument("--prune", action="store_true", help=argparse.SUPPRESS)
    p_init.add_argument("--overwrite-local", action="store_true", help=argparse.SUPPRESS)
    add_selection_flags(p_init)

    p_up = sub.add_parser("update", help="re-copy, keeping locally edited files")
    p_up.add_argument("target", nargs="?", default=".",
                      help="target directory (default: .)")
    p_up.add_argument("--overwrite-local", action="store_true",
                      help="replace files you edited since install")
    p_up.add_argument("--prune", action="store_true",
                      help="delete files the new profile no longer ships")
    p_up.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    add_selection_flags(p_up)

    p_st = sub.add_parser("status", help="show what is installed and what drifted")
    p_st.add_argument("target", nargs="?", default=".",
                      help="target directory (default: .)")
    add_platform_flag(p_st)

    for cmd in ("remove", "undo", "undo-init"):
        p_cmd = sub.add_parser(
            cmd,
            help="delete the installed harness (reverses init)",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        p_cmd.add_argument("target", nargs="?", default=".",
                           help="target directory (default: .)")
        p_cmd.add_argument("--force", action="store_true",
                           help="delete even with local edits or no manifest")
        p_cmd.add_argument("-n", "--dry-run", action="store_true",
                           help="print what would be removed")
        add_platform_flag(p_cmd)

    p_ver = sub.add_parser(
        "verifier",
        help="get or set the verification mode (minimal, compact, full)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Get or set this worktree's verification mode. The setting is untracked\n"
                    "(state/verifier_mode) and overrides the project default chosen at install\n"
                    "with --verifier-mode, so worktrees can verify differently.\n\n"
                    "Modes:\n"
                    "  minimal  - lint checks & non-negotiables only (fastest)\n"
                    "  compact  - Gradle assemble & unit tests (default, no device)\n"
                    "  full     - Gradle assemble, unit tests, and mobilerun app launch\n\n"
                    "Examples:\n"
                    "  aha verifier                          show this worktree's mode\n"
                    "  aha verifier full                     verify on device in this worktree\n"
                    "  aha verifier --reset                  back to the project default\n"
                    "  aha verifier --device emulator-5554   prefer that device when free\n",
    )
    p_ver.add_argument("mode", nargs="?", choices=VERIFIER_MODES, default=None,
                       help=f"verification mode to set ({', '.join(VERIFIER_MODES)})")
    p_ver.add_argument("target", nargs="?", default=".",
                       help="target directory (default: .)")
    p_ver.add_argument("--reset", action="store_true",
                       help="drop this worktree's override and use the project default")
    p_ver.add_argument("--device", "--device-serial", dest="device_serial", default=None,
                       help="device this worktree's lease prefers when free ('' clears it)")
    add_platform_flag(p_ver)

    p_wt = sub.add_parser(
        "worktree",
        help="git worktree add, then install the same harness into it",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Create a git worktree and install the harness this one has -- same\n"
                    "platform, track, profile, verifier default and subagent model. A\n"
                    "committed Claude install arrives with the checkout and is left alone.\n\n"
                    "Examples:\n"
                    "  aha worktree add ../app-login -b feature/login\n"
                    "  aha worktree add ../app-hotfix origin/release\n",
    )
    p_wt.add_argument("--from", dest="source", default=".",
                      help="the installed project to copy the setup from (default: .)")
    add_platform_flag(p_wt)
    p_wt.add_argument("action", choices=["add"])
    p_wt.add_argument("path", help="where to create the worktree")
    p_wt.add_argument("git_args", nargs=argparse.REMAINDER,
                      help="passed to `git worktree add` after the path (e.g. -b <branch>)")

    p_mcp = sub.add_parser(
        "mcp",
        help="show the harness MCP servers, or switch an optional one on or off",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Show or switch the harness MCP servers. mobilerun is not switched here:\n"
                    "it is on in a worktree whose verifier mode is full and off otherwise\n"
                    "(`aha verifier full`). Restart the agent session after a change.\n\n"
                    "Examples:\n"
                    "  aha mcp                 list servers and whether they are on\n"
                    "  aha mcp off figma       stop loading the figma server\n"
                    "  aha mcp on figma\n",
    )
    p_mcp.add_argument("action", nargs="?", choices=["on", "off"], default=None)
    p_mcp.add_argument("names", nargs="*", help="servers to switch (figma)")
    p_mcp.add_argument("--target", default=".", help="target directory (default: .)")
    add_platform_flag(p_mcp)

    p_ls = sub.add_parser("list", help="show available components and profiles")
    p_ls.add_argument("--track", default=DEFAULT_TRACK, choices=TRACKS,
                      help=f"which payload to describe (default: {DEFAULT_TRACK})")

    args = parser.parse_args(argv)

    global SUBAGENT_MODEL
    if args.command == "init":
        select_platform(args.platform or DEFAULT_PLATFORM)
        SUBAGENT_MODEL = args.subagent_model or DEFAULT_SUBAGENT_MODEL
        if args.track is None:
            args.track = DEFAULT_TRACK
        select_track(args.track)
        return do_install(args, updating=False)
    if args.command in ("update", "status", "remove", "undo", "undo-init", "verifier"):
        select_platform(detect_platform(Path(args.target).resolve(), args.platform))
    if args.command == "mcp":
        select_platform(detect_platform(Path(args.target).resolve(), args.platform))
        prev = read_manifest(Path(args.target).resolve() / HARNESS_DIR)
        select_track((prev or {}).get("track", DEFAULT_TRACK))
        return do_mcp(args)
    if args.command == "worktree":
        select_platform(detect_platform(Path(args.source).resolve(), args.platform))
        return do_worktree(args)
    if args.command == "verifier":
        prev = read_manifest(Path(args.target).resolve() / HARNESS_DIR)
        select_track((prev or {}).get("track", DEFAULT_TRACK))
        return do_verifier(args)
    if args.command == "update":
        target_agents = Path(args.target).resolve() / HARNESS_DIR
        prev = read_manifest(target_agents)
        SUBAGENT_MODEL = (args.subagent_model or (prev or {}).get("subagent_model")
                          or DEFAULT_SUBAGENT_MODEL)
        # A flag-less update carries the previous track and profile forward --
        # silently switching a project's toolkit on `aha update` would swap its
        # always-on rules out from under it.
        gave_profile = any(a == "--profile" or a.startswith("--profile=") for a in argv)
        if prev and not gave_profile:
            args.profile = prev.get("profile", "full")
        gave_vmode = any(a == "--verifier-mode" or a.startswith("--verifier-mode=") for a in argv)
        if prev and not gave_vmode:
            args.verifier_mode = prev.get("verifier_mode", DEFAULT_VERIFIER_MODE)
        if args.track is None:
            args.track = (prev or {}).get("track", DEFAULT_TRACK)
        select_track(args.track)
        return do_install(args, updating=True)
    if args.command == "status":
        prev = read_manifest(Path(args.target).resolve() / HARNESS_DIR)
        select_track((prev or {}).get("track", DEFAULT_TRACK))
        SUBAGENT_MODEL = (prev or {}).get("subagent_model") or DEFAULT_SUBAGENT_MODEL
        global MCP_SERVERS, MOBILERUN_ON, VERIFIER_MODE
        VERIFIER_MODE = (prev or {}).get("verifier_mode", DEFAULT_VERIFIER_MODE)
        MCP_SERVERS = (prev or {}).get("mcp_servers")
        MOBILERUN_ON = effective_verifier_mode(
            Path(args.target).resolve() / HARNESS_DIR, VERIFIER_MODE) == "full"
        return do_status(args)
    if args.command in ("remove", "undo", "undo-init"):
        prev = read_manifest(Path(args.target).resolve() / HARNESS_DIR)
        select_track((prev or {}).get("track", DEFAULT_TRACK))
        return do_remove(args)
    if args.command == "list":
        select_track(args.track)
        return do_list(args)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
