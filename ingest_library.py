#!/usr/bin/env python3
"""Safely stage owned loose ROMs or reviewed archive members.

Ambiguous content is reported rather than copied.  `--apply` is required for
writes.  A decision file contains, for example:
{"schema_version": 1, "decisions": {"My Game.iso": "ps2"}}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from lib_thor import atomic_write
from platform_classifier import Classification, canonical_platforms, classify, load_decisions, load_map, review_record

TARGET = Path("/Volumes/Extreme SSD/ayn-thor-card")
ARCHIVES = frozenset({".7z", ".zip", ".rar"})
DANGEROUS = frozenset({".exe", ".scr", ".bat", ".cmd", ".com", ".msi", ".sh", ".command", ".so", ".dylib", ".dll", ".apk", ".jar", ".ps1", ".vbs", ".app"})
MAX_MEMBERS, MAX_MEMBER_BYTES, MAX_TOTAL_BYTES = 512, 32 * 1024**3, 96 * 1024**3

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()

def safe_member_name(name: str) -> bool:
    member = PurePosixPath(name.replace("\\", "/"))
    return bool(name) and not member.is_absolute() and ".." not in member.parts and not any(p in ("", ".") for p in member.parts)

def list_archive(archive: Path) -> list[dict[str, Any]]:
    """Read 7-Zip technical records without extracting archive content."""
    completed = subprocess.run(["7zz", "l", "-slt", "--", str(archive)], capture_output=True, text=True, timeout=120)
    if completed.returncode: raise RuntimeError(completed.stderr.strip() or "7zz could not inspect archive")
    records, record = [], {}
    def append_record() -> None:
        if "Path" in record:
            records.append({"path": record["Path"], "size": int(record.get("Size", "0") or 0), "folder": record.get("Folder", "-") == "+", "attributes": record.get("Attributes", "")})
    for line in completed.stdout.splitlines():
        if not line.strip(): append_record(); record = {}; continue
        if " = " in line:
            key, value = line.split(" = ", 1); record[key] = value
    append_record()
    return [r for r in records if r["path"] != str(archive)]

def validate_members(records: list[dict[str, Any]]) -> list[str]:
    errors, total, seen = [], 0, set()
    if len(records) > MAX_MEMBERS: errors.append(f"too many archive members ({len(records)} > {MAX_MEMBERS})")
    for r in records:
        name, size = r["path"], r["size"]; total += size
        if not safe_member_name(name): errors.append(f"unsafe member path: {name}")
        if name.casefold() in seen: errors.append(f"duplicate member name: {name}")
        seen.add(name.casefold())
        if size < 0 or size > MAX_MEMBER_BYTES: errors.append(f"member exceeds limit: {name}")
        if "l" in r.get("attributes", "").lower(): errors.append(f"symlink-like archive member: {name}")
        if Path(name).suffix.casefold() in DANGEROUS: errors.append(f"dangerous member type: {name}")
    if total > MAX_TOTAL_BYTES: errors.append(f"archive expands beyond limit ({total} bytes)")
    return errors

def extract_member(archive: Path, member: str, work: Path) -> Path:
    # Flattening is only safe for a prevalidated top-level member; never select
    # by basename out of an arbitrary nested archive tree.
    if "/" in member or "\\" in member: raise ValueError("nested archive member requires manual review")
    completed = subprocess.run(["7zz", "e", "-y", f"-o{work}", "--", str(archive), member], capture_output=True, text=True, timeout=3600)
    result = work / member
    if completed.returncode or not result.is_file() or result.is_symlink(): raise RuntimeError("unsafe or failed archive extraction")
    return result

def destination(target: Path, source: Path, c: Classification) -> Path:
    assert c.platform is not None
    rom_path = target / "ROMs"
    if os.path.lexists(rom_path) and rom_path.is_symlink(): raise RuntimeError("target/ROMs must not be a symlink")
    rom_root = rom_path.resolve()
    platform_path = rom_path / c.platform
    if os.path.lexists(platform_path) and platform_path.is_symlink(): raise RuntimeError("target ROM platform directory must not be a symlink")
    result = platform_path / source.name
    try: result.resolve().relative_to(rom_root)
    except ValueError as exc: raise RuntimeError("destination escapes target/ROMs") from exc
    if result.exists() and (result.is_symlink() or not result.is_file()): raise RuntimeError(f"unsafe existing destination: {result}")
    return result

def copy_if_approved(source: Path, target: Path, c: Classification, apply: bool, replace: bool = False, origin: str = "loose") -> dict[str, Any]:
    record = review_record(source, c, source=origin)
    if source.is_symlink(): record["status"] = "rejected_symlink"; return record
    if source.suffix.casefold() in DANGEROUS | ARCHIVES:
        record.update({"status": "rejected_dangerous_or_archive", "reason": "input must be safely inspected as an archive, never copied as a loose file"}); return record
    if c.platform is None: record["status"] = c.confidence; return record
    dest = destination(target, source, c)
    record.update({"sha256": sha256(source), "size_bytes": source.stat().st_size, "destination": str(dest)})
    existed_different = dest.exists()
    if existed_different and dest.stat().st_size == record["size_bytes"] and sha256(dest) == record["sha256"]: record["status"] = "already_present"
    elif existed_different and not replace: record["status"] = "conflict"; record["reason"] = "different destination exists; rerun with --replace after review"
    elif not apply: record["status"] = "planned_replace" if existed_different else "planned"
    else:
        dest.parent.mkdir(parents=True, exist_ok=True); temporary = dest.with_name(dest.name + ".ingest-partial")
        if os.path.lexists(temporary) and temporary.is_symlink(): raise RuntimeError(f"unsafe temporary destination: {temporary}")
        try:
            shutil.copyfile(source, temporary)
            if sha256(temporary) != record["sha256"]: raise RuntimeError("post-copy hash verification failed")
            os.replace(temporary, dest); record["status"] = "replaced" if existed_different else "copied"
        finally:
            temporary.unlink(missing_ok=True)
    return record

def archive_records(archive: Path, target: Path, decisions: dict[str, str], mapping: dict[str, Any], apply: bool, replace: bool = False) -> list[dict[str, Any]]:
    if archive.is_symlink(): return [{"archive": str(archive), "status": "rejected_symlink"}]
    try: members = list_archive(archive)
    except Exception as exc: return [{"archive": str(archive), "status": "unreadable", "error": str(exc)}]
    errors = validate_members(members)
    if errors: return [{"archive": str(archive), "status": "rejected_unsafe_archive", "errors": errors}]
    playable = [m for m in members if not m["folder"] and (lambda c: c.platform is not None or bool(c.candidates))(classify(Path(m["path"]), relative_path=m["path"], decisions=decisions, platform_map=mapping))]
    if len(playable) > 1:
        selection = decisions.get("__archive_members__", {}).get(archive.name)
        if not isinstance(selection, dict) or set(selection) != {"member", "platform"}:
            return [{"archive": str(archive), "status": "needs_review", "reason": "multiple playable archive members; choose one exact member and platform in archive_members", "members": [m["path"] for m in playable]}]
        selected_name, selected_platform = selection["member"], selection["platform"]
        if not isinstance(selected_name, str) or not isinstance(selected_platform, str) or selected_platform not in canonical_platforms(mapping):
            return [{"archive": str(archive), "status": "needs_review", "reason": "archive member selection is malformed or uses a non-canonical platform", "members": [m["path"] for m in playable]}]
        selected = [m for m in playable if m["path"] == selected_name]
        if len(selected) != 1 or "/" in selected_name or "\\" in selected_name:
            return [{"archive": str(archive), "status": "needs_review", "reason": "archive member selection must name exactly one validated top-level playable member", "members": [m["path"] for m in playable]}]
        decisions = {**decisions, selected_name: selected_platform}
        members = selected
    result = []
    for member in members:
        if member["folder"]: continue
        member_path = Path(member["path"]); c = classify(member_path, relative_path=member["path"], decisions=decisions, platform_map=mapping)
        record = review_record(member_path, c, source=f"archive:{archive.name}")
        record.update({"archive": str(archive), "member": member["path"], "member_size_bytes": member["size"]})
        if c.platform is None or "/" in member["path"] or "\\" in member["path"]:
            record["status"] = c.confidence if c.platform is None else "needs_review"; result.append(record); continue
        with tempfile.TemporaryDirectory(prefix="thor-ingest-") as tmp:
            try:
                work = Path(tmp)
                if shutil.disk_usage(work).free < member["size"]: raise RuntimeError("insufficient free temporary space for archive member")
                extracted = extract_member(archive, member["path"], work)
                if extracted.stat().st_size != member["size"]: raise RuntimeError("extracted size differs from inspected archive metadata")
                copied = copy_if_approved(extracted, target, c, apply, replace, f"archive:{archive.name}")
                copied.update({"archive": str(archive), "member": member["path"]}); result.append(copied)
            except Exception as exc: record.update({"status": "extract_failed", "error": str(exc)}); result.append(record)
    return result

def iter_sources(values: Iterable[str]) -> Iterable[Path]:
    for value in values:
        p = Path(value).expanduser()
        # Folders are containers only: recurse to find standalone files but do
        # not copy directory trees or preserve their layout in ROMs/.
        if p.is_dir(): yield from sorted((x for x in p.rglob("*") if x.is_file() and not x.is_symlink()), key=lambda x: x.as_posix().casefold())
        elif p.is_file() and not p.is_symlink(): yield p

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("sources", nargs="+")
    parser.add_argument("--target", type=Path, default=TARGET); parser.add_argument("--decisions", type=Path); parser.add_argument("--apply", action="store_true"); parser.add_argument("--replace", action="store_true", help="allow replacement of a different existing game only with --apply"); parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    try: decisions, mapping = load_decisions(args.decisions), load_map()
    except (ValueError, OSError, json.JSONDecodeError) as exc: parser.error(str(exc))
    records = []
    for source in iter_sources(args.sources):
        if source.is_symlink(): records.append({"source": str(source), "status": "rejected_symlink"}); continue
        if source.suffix.casefold() in ARCHIVES: records.extend(archive_records(source, args.target, decisions, mapping, args.apply, args.replace))
        else:
            try: records.append(copy_if_approved(source, args.target, classify(source, decisions=decisions, platform_map=mapping), args.apply, args.replace))
            except Exception as exc: records.append({"source": str(source), "status": "failed", "error": str(exc)})
    statuses = sorted({r.get("status", "unknown") for r in records})
    manifest = {"schema_version": 2, "mode": "apply" if args.apply else "dry_run", "records": records, "summary": {s: sum(r.get("status") == s for r in records) for s in statuses}, "next_step": "add explicit decisions for every needs_review record, then rerun with --apply"}
    manifest_path = args.manifest or args.target / "ingest-manifest.json"; manifest_path.parent.mkdir(parents=True, exist_ok=True); atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"manifest: {manifest_path}"); print("summary: " + ", ".join(f"{k}={v}" for k, v in manifest["summary"].items()))
    return 1 if any(r.get("status") in {"needs_review", "rejected_unsafe_archive", "rejected_dangerous_or_archive", "rejected_symlink", "conflict", "failed", "extract_failed"} for r in records) else 0

if __name__ == "__main__": raise SystemExit(main())
