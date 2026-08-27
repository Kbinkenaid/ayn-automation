#!/usr/bin/env python3
"""Canonical, read-safe game-library manifest and SSD -> staging synchronizer.

The mounted SSD is the source of truth.  This program never removes files from
it, and it never removes files from the staging tree.  A normal invocation is
a dry run; ``--apply`` is required before a differing staging file is replaced.

Examples:
  python3 thor_library.py scan
  python3 thor_library.py sync                 # report only; no files copied
  python3 thor_library.py sync --apply         # incremental, hash-verified copy
  python3 thor_library.py verify --target sd_card/ROMs
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from lib_thor import atomic_write, sha256_file

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path("/Volumes/Extreme SSD/ayn-thor-card/ROMs")
DEFAULT_TARGET = ROOT / "sd_card" / "ROMs"
DEFAULT_OUTPUT = ROOT / "library"
MANIFEST_VERSION = 1

# Only game/media containers belong in the canonical manifest.  This avoids
# copying ES-DE systeminfo files, Finder metadata, configs, BIOS, and arbitrary
# nested application assets even when they happen to live below ROMs/.
GAME_EXTENSIONS = frozenset({
    ".3ds", ".a26", ".bin", ".chd", ".cia", ".cci", ".cso", ".cue",
    ".dsk", ".fds", ".gcm", ".gb", ".gba", ".gbc", ".gen", ".iso",
    ".m3u", ".n64", ".nds", ".nes", ".nsp", ".pbp", ".rvz",
    ".sfc", ".smc", ".v64", ".wad", ".wbfs", ".wua", ".xci",
    ".z64", ".zip",
})
EXCLUDED_PARTS = frozenset({"bios", "_extras", "__macosx", ".git", ".svn"})
EXCLUDED_NAMES = frozenset({"systeminfo.txt", ".ds_store", "bios-checklist.txt"})


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _relative(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


class TargetSafetyError(RuntimeError):
    """A sync destination is unsafe to inspect or modify."""


def _absolute_no_resolve(path: Path) -> Path:
    """Absolute form without resolving symlinks (which would mask them)."""
    return Path(os.path.abspath(path))


def assert_no_symlink_path(path: Path) -> Path:
    """Reject a path if it or any currently-existing ancestor is a symlink."""
    absolute = _absolute_no_resolve(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        # lexists catches a dangling symlink too; Path.exists() does not.
        # macOS deliberately exposes /var as a compatibility alias for
        # /private/var; allowing only this immutable OS-level alias keeps
        # temporary-directory staging usable without allowing user-controlled
        # redirects anywhere in the target path.
        is_macos_var_alias = current == Path("/var") and current.resolve() == Path("/private/var")
        if os.path.lexists(current) and current.is_symlink() and not is_macos_var_alias:
            raise TargetSafetyError(f"unsafe symlink in staging path: {current}")
    return absolute


class TargetLock:
    """Non-blocking target-scoped advisory lock, stored outside the ROM tree."""

    def __init__(self, output: Path, target: Path):
        self.target = target
        identity = hashlib.sha256(str(_absolute_no_resolve(target)).encode()).hexdigest()[:20]
        self.path = output / ".locks" / f"staging-{identity}.lock"
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            raise TargetSafetyError(
                f"another library operation is already using this staging target: {self.path}"
            ) from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"pid={os.getpid()} target={_absolute_no_resolve(self.target)} started={utc()}\n")
        self.handle.flush()
        return self

    def __exit__(self, *exc):
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def included_file(path: Path, source: Path) -> bool:
    """Return whether *path* is an owned game file, never a support asset."""
    rel = PurePosixPath(_relative(path, source))
    parts_lower = {part.lower() for part in rel.parts}
    if parts_lower & EXCLUDED_PARTS:
        return False
    if path.name.lower() in EXCLUDED_NAMES or path.name.startswith("."):
        return False
    # Only direct children of a known platform directory are game files. This
    # deliberately rejects ROM-root files and nested app/game assets rather
    # than guessing which of their contents should be deployed.
    return len(rel.parts) == 2 and path.suffix.lower() in GAME_EXTENSIONS


def file_role(path: Path) -> str:
    """Conservative informational role only; never used to decide placement."""
    name = path.name.lower()
    if any(token in name for token in ("dlc", "add-on", "addon", "expansion", "booster course")):
        return "dlc"
    if any(token in name for token in ("update", "[upd]", "[v", "[1.", "[2.")):
        return "update"
    return "base_or_unknown"


def scan(source: Path) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"source ROM directory is unavailable: {source}")
    files: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for path in sorted(source.rglob("*"), key=lambda p: p.as_posix().casefold()):
        if path.is_symlink():
            skipped["symlink"] += 1
            continue
        if not path.is_file():
            continue
        if not included_file(path, source):
            skipped["non_game_or_excluded"] += 1
            continue
        stat = path.stat()
        if stat.st_size == 0:
            skipped["zero_byte_game"] += 1
            continue
        rel = _relative(path, source)
        files.append({
            "path": rel,
            "platform": PurePosixPath(rel).parts[0],
            "name": path.name,
            "extension": path.suffix.lower(),
            "role": file_role(path),
            "size_bytes": stat.st_size,
            "sha256": sha256_file(path),
        })
    total = sum(record["size_bytes"] for record in files)
    return {
        "schema_version": MANIFEST_VERSION,
        "generated_at": utc(),
        "source": str(source),
        "file_count": len(files),
        "total_size_bytes": total,
        "files": files,
        "skipped": dict(sorted(skipped.items())),
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def human_size(size: int) -> str:
    return f"{size / (1024 ** 3):.2f} GiB ({size:,} bytes)"


def render_listing(manifest: dict[str, Any]) -> str:
    lines = [
        "AYN Thor game library (canonical SSD scan)",
        f"Generated: {manifest['generated_at']}",
        f"Source: {manifest['source']}",
        f"Total game files: {manifest['file_count']}",
        f"Total storage size: {human_size(manifest['total_size_bytes'])}",
        "",
    ]
    by_platform: dict[str, list[dict[str, Any]]] = {}
    for item in manifest["files"]:
        by_platform.setdefault(item["platform"], []).append(item)
    for platform in sorted(by_platform, key=str.casefold):
        records = by_platform[platform]
        lines.append(f"[{platform}] — {len(records)} files")
        for record in records:
            role = "" if record["role"] == "base_or_unknown" else f" [{record['role']}]"
            lines.append(f"- {record['path']} — {human_size(record['size_bytes'])}{role}")
        lines.append("")
    return "\n".join(lines)


def target_hash(path: Path, expected_size: int) -> str | None:
    if not path.is_file() or path.is_symlink() or path.stat().st_size != expected_size:
        return None
    return sha256_file(path)


def build_plan(manifest: dict[str, Any], target: Path) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for item in manifest["files"]:
        dest = target / PurePosixPath(item["path"])
        try:
            assert_no_symlink_path(dest)
        except TargetSafetyError as exc:
            action, reason = "conflict", str(exc)
        else:
            action, reason = _destination_action(dest, item)
        plan.append({"path": item["path"], "action": action, "reason": reason,
                     "size_bytes": item["size_bytes"], "sha256": item["sha256"]})
    return plan


def _destination_action(dest: Path, item: dict[str, Any]) -> tuple[str, str]:
    if not dest.exists():
        return "copy", "missing"
    if dest.is_symlink() or not dest.is_file():
        return "conflict", "destination is not a regular file"
    digest = target_hash(dest, item["size_bytes"])
    if digest == item["sha256"]:
        return "skip", "hash matches"
    return "replace", "destination hash or size differs"


def partial_paths(destination: Path) -> tuple[Path, Path]:
    partial = destination.with_name(destination.name + ".thor-partial")
    return partial, partial.with_name(partial.name + ".json")


def copy_resumable(source: Path, destination: Path, expected_sha: str) -> None:
    """Copy using a sidecar-tagged partial file, then verify and atomically swap."""
    assert_no_symlink_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial, state = partial_paths(destination)
    # Partial artifacts are executable control points for resume. Never follow
    # them if another process/user has replaced one with a symlink.
    for path in (partial, state):
        if os.path.lexists(path) and path.is_symlink():
            raise TargetSafetyError(f"unsafe symlink in partial-copy path: {path}")
    source_size = source.stat().st_size
    state_ok = False
    try:
        state_ok = json.loads(state.read_text()) == {"sha256": expected_sha, "size_bytes": source_size}
    except (OSError, json.JSONDecodeError):
        pass
    if not state_ok:
        partial.unlink(missing_ok=True)  # own incomplete artifact only
        state.unlink(missing_ok=True)
    if not partial.exists():
        write_json(state, {"sha256": expected_sha, "size_bytes": source_size})
        partial.touch()
    existing = partial.stat().st_size
    if existing > source_size:
        partial.unlink()
        partial.touch()
        existing = 0
    with source.open("rb") as src, partial.open("ab") as dst:
        src.seek(existing)
        shutil.copyfileobj(src, dst, length=4 * 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    if partial.stat().st_size != source_size or sha256_file(partial) != expected_sha:
        raise RuntimeError(f"copy verification failed for {source}")
    os.replace(partial, destination)
    # Persist the rename on filesystems that support directory fsync.
    with contextlib.suppress(OSError):
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    state.unlink(missing_ok=True)


def apply_plan(source: Path, target: Path, plan: Iterable[dict[str, Any]]) -> tuple[list[str], list[dict[str, str]]]:
    completed: list[str] = []
    errors: list[dict[str, str]] = []
    for step in plan:
        if step["action"] == "skip":
            continue
        if step["action"] == "conflict":
            errors.append({"path": step["path"], "error": step["reason"]})
            continue
        try:
            copy_resumable(source / PurePosixPath(step["path"]), target / PurePosixPath(step["path"]), step["sha256"])
            completed.append(step["path"])
        except Exception as exc:  # keep partial files for a later resume
            errors.append({"path": step["path"], "error": str(exc)})
    return completed, errors


def report_for(manifest: dict[str, Any], target: Path, plan: list[dict[str, Any]], applied: bool, completed: list[str] | None = None, errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_VERSION,
        "generated_at": utc(),
        "mode": "apply" if applied else "dry_run",
        "source": manifest["source"],
        "target": str(target.resolve()),
        "source_file_count": manifest["file_count"],
        "source_total_size_bytes": manifest["total_size_bytes"],
        "summary": dict(Counter(step["action"] for step in plan)),
        "plan": plan,
        "completed": completed or [],
        "errors": errors or [],
        "safety": {
            "source_is_read_only": True,
            "implicit_target_deletes": False,
            "replacement_is_atomic_and_hash_verified": True,
            "partial_copies_are_resumable": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scan", "sync", "verify"), nargs="?", default="sync")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="canonical SSD ROMs directory")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="PC staging ROMs directory")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="where manifest/listing/reports are written")
    parser.add_argument("--apply", action="store_true", help="perform copy/atomic replacement; default is dry-run")
    args = parser.parse_args(argv)
    if args.command != "sync" and args.apply:
        parser.error("--apply is valid only with sync")

    # Fail before inspecting/copying anything below a potentially redirected
    # target root. The source is independently canonical and read-only.
    try:
        assert_no_symlink_path(args.target)
        with TargetLock(args.output, args.target):
            manifest = scan(args.source)
            manifest_path = args.output / "canonical-ssd-manifest.json"
            listing_path = args.output / "game-library-directory.txt"
            write_json(manifest_path, manifest)
            listing_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(listing_path, render_listing(manifest))

            plan = build_plan(manifest, args.target)
            completed: list[str] = []
            errors: list[dict[str, str]] = []
            if args.command == "sync" and args.apply:
                completed, errors = apply_plan(args.source.resolve(), args.target, plan)
            report = report_for(manifest, args.target, plan, args.command == "sync" and args.apply, completed, errors)
            report_path = args.output / f"{args.command}-report.json"
            write_json(report_path, report)
    except TargetSafetyError as exc:
        print(f"safety error: {exc}", file=sys.stderr)
        return 2
    print(f"manifest: {manifest_path}")
    print(f"listing:  {listing_path}")
    print(f"report:   {report_path}")
    print("plan: " + ", ".join(f"{k}={v}" for k, v in sorted(report["summary"].items())))
    if errors:
        print(f"errors: {len(errors)}", file=sys.stderr)
        return 1
    if args.command == "verify" and any(step["action"] != "skip" for step in plan):
        print("verification failed: staging differs from the canonical SSD manifest", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
