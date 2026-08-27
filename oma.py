#!/usr/bin/env python3
"""
oma -- inject the Antigravity Android agent harness into any project.

The whole payload is one directory: `.agents/` (rules, skills, agents, hooks,
mcp_config.json). Nothing is written to the target's project root, so `init` is
a self-contained, reversible drop-in.

    python oma.py init   <target>     copy .agents/ into <target>
    python oma.py update <target>     re-copy, keeping locally edited files
    python oma.py status <target>     what is installed, and what drifted
    python oma.py remove <target>     delete the installed harness
    python oma.py list                available components and profiles

Stdlib only. Run `python oma.py <command> --help` for flags.
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

SOURCE_ROOT = Path(__file__).resolve().parent
SOURCE_AGENTS = SOURCE_ROOT / ".agents"
MANIFEST_NAME = ".oma.json"

# Directories and files that are development scaffolding for the harness repo
# itself and have no business in a target project.
EXCLUDES = (
    "state/*",
    "state",
    "evals/*",
    "evals",
    "**/__pycache__/*",
    "**/__pycache__",
    "*.pyc",
    MANIFEST_NAME,
)

# Files whose contents are merged into an existing target file rather than
# overwritten, because a project may already have its own.
MERGEABLE = ("hooks.json", "mcp_config.json")

# Profiles select which skills/agents/rules ship. `full` is the default and is
# defined by absence -- everything on disk. The named subsets are convenience,
# not policy; edit these lists freely.
PROFILES: dict[str, dict[str, list[str]]] = {
    "minimal": {
        "skills": [
            "lean", "lean-audit", "lean-debt", "lean-gain", "lean-help",
            "lean-review", "code-review", "document_project", "loop", "ultrawork",
        ],
        "agents": ["explore", "oracle", "orchestrator", "worker-deep", "worker-quick"],
        "rules": ["orchestrate", "lean"],
    },
    "figma": {
        "skills": [
            "figma-asset-extractor", "figma-design-analyzer", "figma2compose",
            "image-loading-landscapist", "styles", "lean", "lean-review",
        ],
        "agents": [
            "explore", "figma-analyzer", "figma-asset-extractor",
            "figma-compose-developer", "orchestrator",
        ],
        "rules": ["figma", "android", "orchestrate", "lean"],
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
        "agents": ["explore", "oracle", "orchestrator", "worker-deep", "worker-quick"],
        "rules": ["android", "orchestrate", "lean"],
    },
}


# --------------------------------------------------------------------------
# source inspection
# --------------------------------------------------------------------------

def die(msg: str) -> None:
    print(f"oma: {msg}", file=sys.stderr)
    raise SystemExit(1)


def source_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(SOURCE_ROOT), "rev-parse", "--short", "HEAD"],
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
    profile = PROFILES.get(args.profile) if args.profile != "full" else None
    if args.profile != "full" and profile is None:
        die(f"unknown profile {args.profile!r} (have: full, {', '.join(PROFILES)})")

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
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_manifest(target_agents: Path, files: dict[str, str], args) -> None:
    manifest = {
        "source": str(SOURCE_ROOT),
        "commit": source_commit(),
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

    # Files this install no longer ships but a previous one did.
    stale = []
    if manifest:
        shipped = set(files)
        for rel in manifest.get("files", {}):
            if rel not in shipped and (target_agents / rel).is_file() and rel not in state["modified"]:
                stale.append(rel)
                if not args.dry_run and args.prune:
                    (target_agents / rel).unlink()

    if stale and args.prune and not args.dry_run:
        prune_empty_dirs(target_agents)

    if not args.dry_run:
        write_manifest(target_agents, digests, args)

    verb = "would write" if args.dry_run else "wrote"
    print(f"oma {'update' if updating else 'init'} -> {target_agents}")
    print(f"  profile      {args.profile}  (source {source_commit()})")
    print(f"  {verb:<12} {len(written)} file(s)"
          + (f", {unchanged_n} already current" if unchanged_n else ""))
    for rel in merged:
        print(f"  merged       {rel} (your entries kept, harness entries added)")
    for rel in skipped:
        print(f"  kept local   {rel} (edited since install; --overwrite-local to replace)")
    for rel in stale:
        print(f"  {'pruned' if args.prune and not args.dry_run else 'orphaned'}       {rel}"
              + ("" if args.prune else " (no longer in profile; --prune to delete)"))
    if not existing and not args.dry_run:
        print("\nNext: open the project in Antigravity. `.agents/rules/*.md` load always;")
        print("skills load on demand; hooks run with CWD = .agents/ and need `python` on PATH.")
    return 0


def do_status(args) -> int:
    target = Path(args.target).resolve()
    target_agents = target / ".agents"
    if not target_agents.is_dir():
        print(f"oma: no .agents/ in {target}")
        return 1
    manifest = read_manifest(target_agents)
    print(f"oma status -> {target_agents}")
    if not manifest:
        print("  no manifest -- .agents/ exists but was not installed by this CLI")
        return 1

    state = classify(target_agents, manifest)
    print(f"  installed    {manifest.get('installed_at', '?')}"
          f"  profile {manifest.get('profile', '?')}  commit {manifest.get('commit', '?')}")
    print(f"  source       {manifest.get('source', '?')}")

    now = source_commit()
    if manifest.get("commit") not in (now, "unknown"):
        print(f"  SOURCE MOVED source is now {now} -- run `update`")

    outdated = []
    for rel, digest in manifest.get("files", {}).items():
        src = SOURCE_AGENTS / rel
        if src.is_file() and sha256(src) != digest and rel not in state["modified"]:
            outdated.append(rel)

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
        die(f"{target_agents} has no oma manifest -- refusing to delete "
            "a directory this CLI did not install (use --force)")

    state = classify(target_agents, manifest)
    if state["modified"] and not args.force:
        print(f"oma: {len(state['modified'])} file(s) edited since install:")
        for rel in state["modified"][:20]:
            print(f"    {rel}")
        die("refusing to delete local edits -- re-run with --force")

    if args.dry_run:
        print(f"oma: would delete {target_agents}")
        return 0
    shutil.rmtree(target_agents)
    print(f"oma: removed {target_agents}")
    return 0


def do_list(args) -> int:
    print(f"oma source {SOURCE_AGENTS}  (commit {source_commit()})\n")
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
    print("profiles")
    print(f"  {'full':<10} everything above (default)")
    for name, spec in PROFILES.items():
        counts = ", ".join(f"{len(v)} {k}" for k, v in spec.items())
        print(f"  {name:<10} {counts}")
    return 0


# --------------------------------------------------------------------------
# argument parsing
# --------------------------------------------------------------------------

def add_selection_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--profile", default="full",
                   help="full (default), " + ", ".join(PROFILES))
    p.add_argument("--skills", help="comma-separated skill names (overrides profile)")
    p.add_argument("--agents", help="comma-separated agent names (overrides profile)")
    p.add_argument("--rules", help="comma-separated rule names (overrides profile)")
    p.add_argument("--no-skills", action="store_true")
    p.add_argument("--no-agents", action="store_true")
    p.add_argument("--no-rules", action="store_true")
    p.add_argument("--no-hooks", action="store_true", help="skip hooks.json and hooks/")
    p.add_argument("--no-mcp", action="store_true", help="skip mcp_config.json")
    p.add_argument("-n", "--dry-run", action="store_true", help="print the plan only")


def main(argv: list[str]) -> int:
    if not SOURCE_AGENTS.is_dir():
        die(f"no .agents/ next to {Path(__file__).name} -- run this from the harness repo")

    parser = argparse.ArgumentParser(
        prog="oma", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="copy .agents/ into a project")
    p_init.add_argument("target")
    p_init.add_argument("--force", action="store_true",
                        help="proceed even if .agents/ already exists")
    p_init.add_argument("--prune", action="store_true", help=argparse.SUPPRESS)
    p_init.add_argument("--overwrite-local", action="store_true", help=argparse.SUPPRESS)
    add_selection_flags(p_init)

    p_up = sub.add_parser("update", help="re-copy, keeping locally edited files")
    p_up.add_argument("target")
    p_up.add_argument("--overwrite-local", action="store_true",
                      help="replace files you edited since install")
    p_up.add_argument("--prune", action="store_true",
                      help="delete files the new profile no longer ships")
    p_up.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    add_selection_flags(p_up)

    p_st = sub.add_parser("status", help="show what is installed and what drifted")
    p_st.add_argument("target")

    p_rm = sub.add_parser("remove", help="delete the installed harness")
    p_rm.add_argument("target")
    p_rm.add_argument("--force", action="store_true",
                      help="delete even with local edits or no manifest")
    p_rm.add_argument("-n", "--dry-run", action="store_true")

    sub.add_parser("list", help="show available components and profiles")

    args = parser.parse_args(argv)

    if args.command == "init":
        # A profile-less update carries the previous profile forward.
        return do_install(args, updating=False)
    if args.command == "update":
        target_agents = Path(args.target).resolve() / ".agents"
        prev = read_manifest(target_agents)
        gave_profile = any(a == "--profile" or a.startswith("--profile=") for a in argv)
        if prev and not gave_profile:
            args.profile = prev.get("profile", "full")
        return do_install(args, updating=True)
    if args.command == "status":
        return do_status(args)
    if args.command == "remove":
        return do_remove(args)
    if args.command == "list":
        return do_list(args)
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        raise SystemExit(130)
