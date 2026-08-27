#!/usr/bin/env python3
"""Phase 0.5 — capability probe (v2 §6). Non-destructive, self-cleaning,
cached per (serial, android version, security patch).

Usage: python3 probe.py <serial> [--refresh]
Prints the probe table; exits 0. capabilities.json written to ~/.thor-provision/.
"""
import json
import subprocess
import sys
from pathlib import Path

from lib_thor import Adb, STATE_DIR, logger_for, load_state, save_state

PROBES = [
    "appops_writable", "android_data_readable", "android_data_writable",
    "locksettings_available", "settings_write", "uiautomator_dump",
    "screencap", "root", "sd_writable",
]

CANARY_PKG = "com.android.shell"


def device_fingerprint(adb: Adb) -> dict:
    _, model, _ = adb.shell("getprop ro.product.model")
    _, release, _ = adb.shell("getprop ro.build.version.release")
    _, patch, _ = adb.shell("getprop ro.build.version.security_patch")
    return {"model": model, "release": release, "patch": patch}


def run_probe(name: str, adb: Adb, rom_root: str | None) -> tuple[bool, str]:
    try:
        if name == "appops_writable":
            adb.shell(f"appops set {CANARY_PKG} MANAGE_EXTERNAL_STORAGE allow", check=False)
            _, got, _ = adb.shell(f"appops get {CANARY_PKG} MANAGE_EXTERNAL_STORAGE", check=False)
            ok = "allow" in got.lower()
            adb.shell(f"appops set {CANARY_PKG} MANAGE_EXTERNAL_STORAGE default", check=False)  # restore
            return ok, got
        if name == "android_data_readable":
            # find any installed 3rd-party package with an Android/data dir
            _, out, _ = adb.shell("ls /sdcard/Android/data | head -40", check=False)
            for pkg in [l.strip() for l in out.splitlines() if l.strip()]:
                rc, o2, _ = adb.shell(f"ls /sdcard/Android/data/{pkg}/files 2>/dev/null", check=False)
                if rc == 0:
                    return True, pkg
            return False, "no readable files dir"
        if name == "android_data_writable":
            probe_pkg = None
            _, out, _ = adb.shell("ls /sdcard/Android/data | head -40", check=False)
            for pkg in [l.strip() for l in out.splitlines() if l.strip()]:
                rc, _, _ = adb.shell(f"test -d /sdcard/Android/data/{pkg}/files && echo y", check=False)
                if rc == 0:
                    probe_pkg = pkg
                    break
            if not probe_pkg:
                return False, "no writable candidate"
            t = f"/sdcard/Android/data/{probe_pkg}/files/.thor-probe"
            adb.shell(f"echo x > '{t}'", check=False)
            rc, got, _ = adb.shell(f"cat '{t}' 2>/dev/null", check=False)
            adb.shell(f"rm -f '{t}'", check=False)
            return (rc == 0 and got.strip() == "x"), probe_pkg
        if name == "locksettings_available":
            rc, _, _ = adb.shell("locksettings help", check=False)
            return rc == 0, ""
        if name == "settings_write":
            adb.shell("settings put system thor_probe_canary 1", check=False)
            _, got, _ = adb.shell("settings get system thor_probe_canary", check=False)
            adb.shell("settings delete system thor_probe_canary", check=False)
            return got.strip() == "1", got
        if name == "uiautomator_dump":
            _, out, _ = adb.shell("uiautomator dump /sdcard/thor-ui.xml", check=False)
            rc, xml, _ = adb.shell("head -c 400 /sdcard/thor-ui.xml 2>/dev/null", check=False)
            adb.shell("rm -f /sdcard/thor-ui.xml", check=False)
            return ("<hierarchy" in xml), f"{len(xml)}B"
        if name == "screencap":
            p = subprocess.run(adb._base() + ["exec-out", "screencap", "-p"],
                               capture_output=True, timeout=30)
            return (p.returncode == 0 and len(p.stdout) > 1000
                    and p.stdout[:4] == b"\x89PNG"), f"{len(p.stdout)}B"
        if name == "root":
            rc, out, _ = adb.shell("su -c id", check=False)
            return (rc == 0 and "uid=0" in out), out[:40]
        if name == "sd_writable":
            root = rom_root or "/sdcard"
            t = f"{root}/.thor-probe"
            adb.shell(f"mkdir -p {root} && echo x > '{t}'", check=False)
            rc, got, _ = adb.shell(f"cat '{t}' 2>/dev/null", check=False)
            adb.shell(f"rm -f '{t}'", check=False)
            return (rc == 0 and got.strip() == "x"), root
    except Exception as e:
        return False, str(e)[:120]
    return False, "unknown probe"


def main(argv: list[str] | None = None) -> int:
    """Probe one explicitly selected device; never infer a target from adb devices."""
    argv = list(sys.argv[1:] if argv is None else argv)
    refresh = "--refresh" in argv
    positional = [arg for arg in argv if arg != "--refresh"]
    if len(positional) != 1 or positional[0].startswith("-"):
        print("usage: probe.py SERIAL [--refresh] (an explicit serial is required)", file=sys.stderr)
        return 2
    serial = positional[0]
    if not serial:
        print("no device", file=sys.stderr)
        return 2

    cap_path = STATE_DIR / "capabilities.json"
    cache = {}
    try:
        cache = json.loads(cap_path.read_text())
    except Exception:
        pass

    with logger_for(serial) as log:
        adb = Adb(serial, log)
        fp = device_fingerprint(adb)
        key = f"{serial}|{fp['release']}|{fp['patch']}"
        state = load_state()
        rom_root = (state.get("devices", {}).get(serial, {}) or {}).get("rom_root_on_device")

        if key in cache and not refresh:
            caps = cache[key]
            print(f"capabilities cached for {fp['model']} (Android {fp['release']}, patch {fp['patch']})")
        else:
            caps = {}
            for name in PROBES:
                ok, detail = run_probe(name, adb, rom_root)
                caps[name] = {"ok": ok, "detail": detail}
                print(f"{'PASS' if ok else 'FAIL'}  {name:26s} {detail}")
            cache[key] = caps
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            cap_path.write_text(json.dumps(cache, indent=2))
            print()

        print(f"== capability report — {fp['model']} (Android {fp['release']}, patch {fp['patch']}) ==")
        for name in PROBES:
            e = caps.get(name, {})
            print(f"  {'✓' if e.get('ok') else '✗'} {name}")
        n_ok = sum(1 for name in PROBES if caps.get(name, {}).get('ok'))
        print(f"\n{n_ok}/{len(PROBES)} available.")
        if not caps.get("android_data_writable", {}).get("ok"):
            print("→ direct emulator-config writes unavailable; configs become checklist items")
        else:
            print("→ direct config writes enabled (Phase 7)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
