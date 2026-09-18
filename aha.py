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

    python aha.py init      [target]  copy the selected track into [target] (default: .)
    python aha.py update    [target]  re-copy, keeping locally edited files
    python aha.py status    [target]  what is installed, and what drifted
    python aha.py undo      [target]  cleanly reverses init, keeping non-AHA files
    python aha.py undo-init [target]  alias for undo
    python aha.py remove    [target]  alias for undo
    python aha.py list                available components and profiles

    aha init --track xml              a View/XML project
    aha init                          Compose (the default)

Stdlib only. Run `python aha.py <command> --help` for flags.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
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
TRACKS = ("compose", "xml")
DEFAULT_TRACK = "compose"

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
                "gradle-run", "scrcpy",
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
                "orbit-mvi-feature-builder", "gradle-run", "testing-setup", "scrcpy",
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
                "scrcpy", "styles", "testing-setup", "translate-strings", "ultrawork",
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
                "gradle-run", "scrcpy",
            ],
            "agents": ["explore", "oracle", "orchestrator", "executor", "verifier"],
            "rules": ["lean"],
        },
        "figma": {
            "skills": [
                "figma-asset-extractor", "figma-design-analyzer", "figma2xml",
                "shape-view", "image-loading-glide", "android-xml-views",
                "xml-resource-policy", "lean", "lean-review", "android-code-indexer",
                "gradle-run", "testing-setup", "scrcpy",
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
                "r8-analyzer", "scrcpy", "shape-view", "testing-setup",
                "translate-strings", "ultrawork", "xml-resource-policy",
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
            files.append(rel)
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
    src = SOURCE_ROOT / ROOT_DOC
    return src.read_text(encoding="utf-8").strip() if src.is_file() else ""


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


def merged_text(rel: str, src: Path, dst: Path) -> str:
    if rel == "mcp_config.json":
        return merge_json(src, dst, "mcpServers")
    if rel == "hooks.json":
        return merge_json(src, dst, None)
    return src.read_text(encoding="utf-8")


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


def write_manifest(target_agents: Path, files: dict[str, str], args) -> None:
    manifest = {
        "source": str(SOURCE_ROOT),
        "commit": source_commit(),
        "track": args.track,
        "profile": args.profile,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
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
    target_agents = target / ".agents"
    if target_agents.resolve() == SOURCE_AGENTS.resolve():
        die("target is the harness source itself")
    if target == REPO_ROOT:
        die("the harness repo keeps no .agents/ of its own -- edit assets/ instead")

    manifest = read_manifest(target_agents)
    existing = target_agents.exists()

    if existing and not updating and not args.force:
        die(f"{target_agents} already exists -- use `update`, or `init --force`")

    state = classify(target_agents, manifest)
    protected = set(state["modified"]) if (updating and not args.overwrite_local) else set()

    selection = resolve_selection(args)
    files = plan_files(selection, include_hooks=not args.no_hooks,
                       include_mcp=not args.no_mcp)
    if not files:
        die("selection is empty -- nothing to install")

    written, skipped, merged, unchanged_n = [], [], [], 0
    digests: dict[str, str] = {}

    for rel in files:
        src = SOURCE_AGENTS / rel
        dst = target_agents / rel
        if rel in protected:
            skipped.append(rel)
            digests[rel] = manifest["files"][rel] if manifest else sha256(src)
            continue

        text = None
        if rel in MERGEABLE and dst.is_file() and manifest is None:
            text = merged_text(rel, src, dst)
            merged.append(rel)

        if not args.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if text is None:
                if dst.is_file() and sha256(dst) == sha256(src):
                    unchanged_n += 1
                    digests[rel] = sha256(src)
                    continue
                shutil.copy2(src, dst)
            else:
                dst.write_text(text, encoding="utf-8")
            digests[rel] = sha256(dst)
        else:
            digests[rel] = sha256(src)
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

    if not args.dry_run:
        write_manifest(target_agents, digests, args)

    exclude_status = None
    exclude_n = 0
    if not args.no_git_exclude:
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
    print(f"  track        {args.track}")
    print(f"  profile      {args.profile}  (source {source_commit()})")
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
    for rel in skipped:
        print(f"  kept local   {rel} (edited since install; --overwrite-local to replace)")
    for rel in stale:
        print(f"  {'pruned' if args.prune and not args.dry_run else 'orphaned'}       {rel}"
              + ("" if args.prune else " (no longer in profile; --prune to delete)"))
    if not existing and not args.dry_run:
        print("\nNext: open the project in Antigravity. `AGENTS.md` and `.agents/rules/*.md`")
        print("load always; skills load on demand; hooks run with CWD = .agents/ and need")
        print("`python` on PATH.")
    return 0


def do_status(args) -> int:
    target = Path(args.target).resolve()
    target_agents = target / ".agents"
    if not target_agents.is_dir():
        print(f"aha: no .agents/ in {target}")
        return 1
    manifest = read_manifest(target_agents)
    print(f"aha status -> {target_agents}")
    if not manifest:
        print("  no manifest -- .agents/ exists but was not installed by this CLI")
        return 1

    state = classify(target_agents, manifest)
    print(f"  installed    {manifest.get('installed_at', '?')}"
          f"  track {manifest.get('track', DEFAULT_TRACK)}"
          f"  profile {manifest.get('profile', '?')}  commit {manifest.get('commit', '?')}")
    print(f"  source       {manifest.get('source', '?')}")

    now = source_commit()
    if manifest.get("commit") not in (now, "unknown"):
        print(f"  SOURCE MOVED source is now {now} -- run `update`")

    outdated = []
    for rel, digest in manifest.get("files", {}).items():
        if rel == ROOT_DOC_KEY:
            continue
        src = SOURCE_AGENTS / rel
        if src.is_file() and sha256(src) != digest and rel not in state["modified"]:
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
    target_agents = target / ".agents"
    if not target_agents.is_dir():
        die(f"no .agents/ in {target}")
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

    exclude_path = git_exclude_file(target)
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

    if root_action == "delete":
        root_dst.unlink()
        print(f"aha: removed {root_dst}")
    elif root_action == "unsplice":
        kept = strip_block(root_dst.read_text(encoding="utf-8")) + "\n"
        with root_dst.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(kept)
        print(f"aha: removed our block from {root_dst}, kept your content")
    return 0


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

def add_selection_flags(p: argparse.ArgumentParser) -> None:
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
    p.add_argument("--no-mcp", action="store_true", help="skip mcp_config.json")
    p.add_argument("--no-agents-md", action="store_true",
                   help=f"skip {ROOT_DOC} (leaves the project root untouched)")
    p.add_argument("--no-git-exclude", action="store_true",
                   help="skip updating .git/info/exclude")
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

    p_ls = sub.add_parser("list", help="show available components and profiles")
    p_ls.add_argument("--track", default=DEFAULT_TRACK, choices=TRACKS,
                      help=f"which payload to describe (default: {DEFAULT_TRACK})")

    args = parser.parse_args(argv)

    if args.command == "init":
        if args.track is None:
            args.track = DEFAULT_TRACK
        select_track(args.track)
        return do_install(args, updating=False)
    if args.command == "update":
        target_agents = Path(args.target).resolve() / ".agents"
        prev = read_manifest(target_agents)
        # A flag-less update carries the previous track and profile forward --
        # silently switching a project's toolkit on `aha update` would swap its
        # always-on rules out from under it.
        gave_profile = any(a == "--profile" or a.startswith("--profile=") for a in argv)
        if prev and not gave_profile:
            args.profile = prev.get("profile", "full")
        if args.track is None:
            args.track = (prev or {}).get("track", DEFAULT_TRACK)
        select_track(args.track)
        return do_install(args, updating=True)
    if args.command == "status":
        prev = read_manifest(Path(args.target).resolve() / ".agents")
        select_track((prev or {}).get("track", DEFAULT_TRACK))
        return do_status(args)
    if args.command in ("remove", "undo", "undo-init"):
        prev = read_manifest(Path(args.target).resolve() / ".agents")
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
