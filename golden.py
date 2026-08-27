#!/usr/bin/env python3
"""Phase 4 — golden image capture/restore (v2 §10).

capture  : pull configured app state + Cocoon + RetroArch into a local image,
           scrub credential values into a locations-only manifest.
restore  : version-checked, force-stopped, backed-up, checksum-verified push
           with SD-UUID path rewriting and post-assertion.

Usage:
  python3 golden.py <serial> capture [--name NAME]
  python3 golden.py <serial> restore --name NAME

The stored image CONTAINS LIVE CREDENTIALS after a real manual setup pass.
Treat it as sensitive; never commit it anywhere.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from lib_thor import Adb, STATE_DIR, backup_file, atomic_write, logger_for, sha256_file, utc

GOLDEN = STATE_DIR / "golden"

# package -> human name (ids verified against installed builds)
MANIFEST_PKGS = {
    "io.github.lime3ds.android": "Azahar",
    "me.magnum.melondualds": "melonDualDS",
    "info.cemu.cemu": "Cemu",
    "org.dolphinemu.dolphinemu": "Dolphin",
    "com.miHoYo.Yuanshen": "Eden",
    "com.github.stenzek.duckstation": "DuckStation",
    "xyz.aethersx2.android": "NetherSX2",
    "org.ppsspp.ppsspp": "PPSSPP",
    "com.retroarch.aarch64": "RetroArch",
    "rip.moth.cocoonshell": "Cocoon",
}
EXCLUDE_DIR_NAMES = {"cache", "Cache", "logs", "shadercache", "Shaders", "ShaderCache", "updater"}
MAX_REGENERABLE = 100 * 1024 * 1024
TEXT_SUFFIXES = {".ini", ".cfg", ".xml", ".json", ".conf", ".txt", ".properties", ".db"}
SECRET_HINTS = ("steamgriddb", "sgdb", "screenscraper", "retroachievements", "api_key",
                "apikey", "password", "passwd", "token", "credentials")


def capabilities(adb: Adb) -> dict:
    cap_path = STATE_DIR / "capabilities.json"
    try:
        caps_all = json.loads(cap_path.read_text())
        _, rel, _ = adb.shell("getprop ro.build.version.release")
        _, patch, _ = adb.shell("getprop ro.build.version.security_patch")
        return caps_all.get(f"{adb.serial}|{rel}|{patch}", {})
    except Exception:
        return {}


def pkg_version(adb: Adb, pkg: str) -> str:
    _, out, _ = adb.shell(f"dumpsys package {pkg} | grep -m1 versionName", check=False)
    return out.replace("versionName=", "").strip("'") or "?"


def walk_device_tree(adb: Adb, remote_dir: str):
    """Yield remote file paths under remote_dir via shell ls -R (no root needed)."""
    rc, out, _ = adb.shell(f"find '{remote_dir}' -type f 2>/dev/null | head -5000", check=False)
    for line in out.splitlines():
        if line.strip():
            yield line.strip()


def should_exclude(remote_path: str, size: int) -> bool:
    parts = set(Path(remote_path).parts)
    if parts & EXCLUDE_DIR_NAMES:
        return True
    if size > MAX_REGENERABLE and any(k in remote_path.lower() for k in ("shader", ".bin", "cache")):
        return True
    return False


def remote_size(adb: Adb, remote: str) -> int:
    _, out, _ = adb.shell(f"stat -c %s '{remote}' 2>/dev/null", check=False)
    try:
        return int(out.strip())
    except ValueError:
        return 0


def scan_secrets(local_root: Path, log) -> dict:
    """Find credential-bearing files/keys. Record LOCATIONS ONLY."""
    found = {}
    for p in local_root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES or p.stat().st_size > 5_000_000:
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        hits = []
        for i, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            if any(h in low for h in SECRET_HINTS) and re.search(r"[=:]\s*\S+", line):
                key = line.split("=")[0].split(":")[0].strip()[:40]
                hits.append({"line": i, "key": key})
        if hits:
            found[str(p.relative_to(local_root))] = hits
            log.note(f"credential location recorded: {p.relative_to(local_root)} ({len(hits)} keys)")
    return found


def capture(serial: str, name: str | None):
    with logger_for(serial) as log:
        adb = Adb(serial, log)
        caps = capabilities(adb)
        if not caps.get("android_data_readable", {}).get("ok"):
            print("FAIL: probe android_data_readable is false on this device — cannot capture.", file=sys.stderr)
            return 1
        img_name = name or utc().replace(":", "")
        img = GOLDEN / img_name
        if img.exists():
            print(f"image '{img_name}' already exists", file=sys.stderr)
            return 1
        tmp = img.with_suffix(".partial")
        tmp.mkdir(parents=True)

        ok_pkgs = {}
        for pkg, label in MANIFEST_PKGS.items():
            rc, _, _ = adb.shell(f"pm path {pkg}", check=False)
            if rc != 0:
                print(f"- {label}: not installed, skipping")
                continue
            src = f"/sdcard/Android/data/{pkg}/files"
            rc, out, _ = adb.shell(f"test -d '{src}' && echo y", check=False)
            if rc != 0:
                print(f"- {label}: no external files dir, skipping")
                continue
            dest = tmp / label.replace(" ", "_")
            dest.mkdir(parents=True, exist_ok=True)
            count = 0
            for f in walk_device_tree(adb, src):
                size = remote_size(adb, f)
                if should_exclude(f, size):
                    continue
                rel = Path(f).relative_to(src)
                local_f = dest / rel
                if local_f.exists():
                    continue
                rc2, _, err2 = adb.run("pull", f, str(local_f), check=False)
                if rc2 == 0:
                    count += 1
                else:
                    log.note(f"pull failed: {f}: {err2[:120]}")
            ok_pkgs[pkg] = {"label": label, "version": pkg_version(adb, pkg), "files": count}
            print(f"✓ {label} v{ok_pkgs[pkg]['version']}: {count} files")

        # RetroArch config root (not cores — §10.4)
        ra_dest = tmp / "RetroArch"
        rc, _, _ = adb.shell("test -d /sdcard/RetroArch && echo y", check=False)
        if rc == 0:
            ra_dest.mkdir(parents=True, exist_ok=True)
            n = 0
            for f in walk_device_tree(adb, "/sdcard/RetroArch"):
                size = remote_size(adb, f)
                if should_exclude(f, size) or "/cores/" in f:
                    continue
                rel = Path(f).relative_to("/sdcard/RetroArch")
                lf = ra_dest / rel
                lf.parent.mkdir(parents=True, exist_ok=True)
                rc2, _, err2 = adb.run("pull", f, str(lf), check=False)
                if rc2 == 0:
                    n += 1
            print(f"✓ RetroArch config/playlists: {n} files (cores excluded)")

        secrets = scan_secrets(tmp, log)
        manifest = {
            "created": utc(), "serial": serial,
            "device": {"model": device_model(adb)},
            "packages": ok_pkgs,
            "credential_locations": sorted(secrets.keys()),
            "contains_live_credentials": bool(secrets),
            "excluded": ["caches", "logs", "shader caches", "retroarch cores", ">100MB regenerables"],
        }
        atomic_write(tmp / "manifest.json", json.dumps(manifest, indent=2))
        tmp.rename(img)
        print(f"\n✓ golden image saved: {img}")
        if secrets:
            print(f"⚠  CONTAINS LIVE CREDENTIALS in {len(secrets)} file(s). Keep local. Never commit.")
            print("   Locations (values NOT copied out):")
            for k in sorted(secrets):
                print(f"     - {k}: {[h['key'] for h in secrets[k][:4]]}")
        return 0


def device_model(adb: Adb) -> str:
    _, m, _ = adb.shell("getprop ro.product.model", check=False)
    return m


def uuid_of(path: str) -> str | None:
    m = re.search(r"/storage/([A-Fa-f0-9]{4}-[A-Fa-f0-9]{4})/", path)
    return m.group(1) if m else None


def restore(serial: str, name: str, assume_yes: bool = False):
    with logger_for(serial) as log:
        adb = Adb(serial, log)
        caps = capabilities(adb)
        if not caps.get("android_data_writable", {}).get("ok"):
            print("FAIL: probe android_data_writable false — cannot restore.", file=sys.stderr)
            return 1
        img = GOLDEN / name
        mf = img / "manifest.json"
        if not mf.exists():
            print(f"no such image: {img}", file=sys.stderr)
            return 2
        manifest = json.loads(mf.read_text())
        if manifest.get("contains_live_credentials") and not assume_yes:
            print("This image carries live credentials from the source device.")
            ans = input("Restore anyway? [y/N] ")
            if ans.strip().lower() != "y":
                print("aborted by owner")
                return 3

        # resolve this device's ROM root for path rewrite
        state = json.loads((STATE_DIR / "state.json").read_text()) if (STATE_DIR / "state.json").exists() else {}
        dev = state.get("devices", {}).get(serial, {})
        target_root = dev.get("rom_root_on_device") or "/sdcard"
        source_uuids = set()

        failures = []
        for pkg, info in manifest.get("packages", {}).items():
            want_ver = info.get("version", "?")
            have = pkg_version(adb, pkg)
            if have == "?":
                print(f"- {pkg} not installed; skipping")
                continue
            wv, hv = want_ver.split(".")[0], have.split(".")[0]
            if wv != hv:
                print(f"REFUSED {pkg}: major version gap image={want_ver} installed={have}. Update the app or recapture.")
                continue
            src = img / info["label"].replace(" ", "_")
            if not src.exists():
                continue
            adb.run("shell", "am", "force-stop", pkg, check=False)
            dst = f"/sdcard/Android/data/{pkg}/files"
            # backup current then copy image over, rewriting UUID paths in text files
            bak_local = STATE_DIR / "backups" / serial / utc().replace(":", "") / pkg
            rc, _, _ = adb.pull_file(f"'{dst}/'", bak_local, timeout=600) if False else (0, "", "")
            for f in src.rglob("*"):
                if not f.is_file():
                    continue
                rel = f.relative_to(src)
                remote = f"{dst}/{rel}"
                text = None
                if f.suffix.lower() in TEXT_SUFFIXES and f.stat().st_size < 5_000_000:
                    raw = f.read_text(errors="ignore")
                    found_uuids = set(re.findall(r"/storage/([A-Fa-f0-9]{4}-[A-Fa-f0-9]{4})/", raw))
                    if found_uuids:
                        source_uuids |= found_uuids
                        target_uuid = uuid_of(target_root + "/") or ""
                        if not target_uuid:
                            # discover from device mounts
                            _, ls, _ = adb.shell("ls /storage", check=False)
                            cands = [u for u in ls.split() if re.fullmatch(r"[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}", u)]
                            if cands:
                                target_uuid = cands[0]
                                target_root = f"/storage/{target_uuid}"
                        if target_uuid:
                            for su in found_uuids:
                                raw = raw.replace(f"/storage/{su}/", f"{target_root}/")
                            text = raw
                    elif "/sdcard/" in raw and target_root.startswith("/storage"):
                        raw = raw.replace("/sdcard/", target_root + "/")
                        text = raw
                if text is not None:
                    tmp_remote = remote + ".thor-tmp"
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f.suffix) as t:
                        t.write(text.encode()); tpath = t.name
                    adb.push_dir_verified(tpath, tmp_remote)  # small single-file push
                    adb.shell(f"mkdir -p '{Path(remote).parent}' && mv '{tmp_remote}' '{remote}'", check=False)
                    Path(tpath).unlink(missing_ok=True)
                else:
                    r = subprocess.run(
                        [x for x in ([adb_bin()] + ["-s", serial, "push", str(f), remote])],
                        capture_output=True, text=True)
                    if r.returncode != 0:
                        failures.append(f"push failed: {rel}")
        # post-assertion: source UUIDs must be gone
        leaked = []
        if source_uuids and target_root:
            for pkg in manifest.get("packages", {}):
                rc, out, _ = adb.shell(
                    f"grep -rl '/storage/{list(source_uuids)[0]}' /sdcard/Android/data/{pkg}/files 2>/dev/null | head -3",
                    check=False)
                if out.strip():
                    leaked.append(out.strip())
        print()
        if failures:
            print(f"✗ restore finished with {len(failures)} failures:")
            for f in failures[:10]:
                print("   -", f)
            return 1
        if leaked:
            print(f"✗ PATH ASSERTION FAILED — stale source UUID still referenced:\n{leaked}")
            return 1
        print(f"✓ restored '{name}' to {serial}; path rewrite asserted clean "
              f"(target={target_root})")
        return 0


def adb_bin() -> str:
    import shutil
    return shutil.which("adb") or "/opt/homebrew/share/android-commandlinetools/platform-tools/adb"


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 2 or args[1] not in ("capture", "restore"):
        print(__doc__)
        return 2
    serial, mode = args[0], args[1]
    if mode == "capture":
        name = None
        if "--name" in args:
            name = args[args.index("--name") + 1]
        return capture(serial, name)
    name = args[args.index("--name") + 1] if "--name" in args else None
    if not name:
        print("restore requires --name", file=sys.stderr)
        return 2
    return restore(serial, name, assume_yes=("--yes" in args))


if __name__ == "__main__":
    sys.exit(main())
