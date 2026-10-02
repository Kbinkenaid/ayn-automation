#!/usr/bin/env python3
"""Build the OFFLINE KIT: everything needed for full Thor setup with zero
internet and zero live GitHub/API dependency.

Generates into configs/offline-kit/:
  - apply-sheets/<emulator>.md   hand-entry settings per emulator (from profile)
  - OWNER-SUPPLY-CHECKLIST.md    BIOS/keys/firmware you must provide yourself
  - kit-manifest.json            every staged artifact + SHA-256 + purpose
  - STORAGE-VARIANTS.md          sd card vs internal vs OTG decision guide

Run BEFORE device day; re-run after any library/APK change.
The kit makes setup fully offline: apks/, driver, configs, checklists, and
the verified library manifest all live on disk already.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from lib_thor import sha256_file, atomic_write  # noqa: E402

KIT = ROOT / "configs" / "offline-kit"
APKS = ROOT / "apks"
DRIVERS = ROOT / "vendor" / "drivers"
PROFILE = ROOT / "profiles" / "ayn-thor-v1.json"
STAGING = ROOT / "sd_card"
LIBRARY = ROOT / "library"

# Exact files each emulator expects the OWNER to supply (never staged by us)
OWNER_SUPPLIES = {
    "RetroArch": {
        "dest": "${ROM_ROOT}/BIOS/",
        "files": [
            "gba_bios.bin (GBA)", "bios7.bin, bios9.bin, firmware.bin (NDS via RetroArch)",
            "saturn BIOS: sega_101.bin or mpr-17933.bin",
            "dreamcast: dc_boot.bin + dc_flash.bin",
        ],
        "note": "Only for systems you actually own carts/discs for.",
    },
    "WatermelonDS": {
        "dest": "${ROM_ROOT}/BIOS/ or in-app folder pick",
        "files": ["bios7.bin", "bios9.bin", "firmware.bin"],
        "note": "Optional for most games; required for some (e.g. DSi mode).",
    },
    "Azahar / AzaharPlus": {
        "dest": "in-app user folder (AES_keys via app)",
        "files": ["AES keys only if you own encrypted dumps (seed .cxi not needed for plaintext)"],
        "note": "Decrypted .3ds/.cci dumps need no keys.",
    },
    "Eden": {
        "dest": "in-app picker: keys + firmware",
        "files": ["prod.keys (your own dump)", "firmware .nca/.nsp package (matching your Switch)"],
        "note": "Never automate copying these; the app picker flow keeps them out of automation.",
    },
    "Cemu / CemuDS": {
        "dest": "in-app: keys.txt via MLC pick",
        "files": ["keys.txt (your own dump)"],
        "note": "Wii U .wua/.wud titles you own.",
    },
    "DuckStation": {
        "dest": "${ROM_ROOT}/BIOS/",
        "files": ["scph1001.bin / scph5501.bin / scph7001.bin (PS1 BIOS, your dump)"],
        "note": "One region is enough; JP/US/EU all work.",
    },
    "NetherSX2": {
        "dest": "in-app BIOS import",
        "files": ["ph_bios.bin / ps2-0200a.bin etc (PS2 BIOS, your dump)"],
        "note": "Single BIOS file covers all regions.",
    },
    "aPS3e": {
        "dest": "in-app Install Firmware action",
        "files": ["PS3UPDAT.PUP (official firmware from your PS3)", "Compatible PS3 ISO/folder dump"],
        "note": "Firmware and games are owner-supplied; never stage them in this repository.",
    },
    "Dolphin": {
        "dest": "in-app (usually none needed)",
        "files": ["Optional: GBAsys BIOS only for GBA connectivity features"],
        "note": "GC/Wii emulation ships BIOS-free in Dolphin.",
    },
    "PPSSPP / Flycast": {"dest": "none", "files": [], "note": "No BIOS required."},
}


def kit_hash(path: Path) -> dict:
    return {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def build_apply_sheets(profile: dict) -> list[Path]:
    """Per-emulator markdown sheet: exact settings to enter by hand."""
    sheets = []
    out = KIT / "apply-sheets"
    out.mkdir(parents=True, exist_ok=True)
    for name, e in profile["emulators"].items():
        rec = e.get("recommended", {})
        lines = [
            f"# {name.upper()} — offline apply sheet",
            "",
            "Enter these settings on device (from profiles/ayn-thor-v1.json).",
            "No internet needed; this sheet is generated from the local profile.",
            "",
            "## Settings",
            "",
        ]
        if rec:
            for k, v in rec.items():
                lines.append(f"- **{k}**: `{v}`")
        else:
            lines.append("- (no recommended overrides; app defaults)")
        controls = e.get("controls")
        if controls:
            lines += ["", "## Physical controls and overlay", "",
                      "Apply these mappings to the emulator's default profile after the Thor controller is detected.",
                      "The exact menu names vary by app; verify one game before saving the profile.", ""]
            lines.append(f"- **physical layout**: `{controls.get('physical_layout', 'device_default')}`")
            mapping = controls.get("profile", controls.get("profiles", {}))
            lines.append("- **button mapping:**")
            for profile_name, profile_map in (mapping.items() if mapping and all(isinstance(v, dict) for v in mapping.values()) else [("default", mapping)]):
                if profile_name != "default":
                    lines.append(f"  - **{profile_name}:**")
                for button, physical in profile_map.items():
                    lines.append(f"    - `{button}` → `{physical}`")
            overlay = controls.get("overlay", {})
            lines.append(f"- **overlay visible**: `{overlay.get('visible', True)}`")
            lines.append(f"- **overlay opacity**: `{overlay.get('opacity', 100)}`")
        lines += ["", "## Manual tasks (in order)", ""]
        for i, task in enumerate(e.get("manual", []), 1):
            lines.append(f"{i}. {task}")
        appearance = e.get("appearance")
        if appearance:
            lines += ["", "## Appearance / decoration", ""]
            for k, v in appearance.items():
                if k == "manual_tasks":
                    lines.append("### Steps")
                    lines.append("")
                    for i, t in enumerate(v, 1):
                        lines.append(f"{i}. {t}")
                else:
                    lines.append(f"- **{k}**: {v if isinstance(v, str) else json.dumps(v)}")
        lines += ["", "## Owner-supplied (you provide; never staged)",
                  "", f"- Destination: {OWNER_SUPPLIES.get(name, {}).get('dest', 'in-app')}"]
        for f in OWNER_SUPPLIES.get(name, {}).get("files", []):
            lines.append(f"- {f}")
        if OWNER_SUPPLIES.get(name, {}).get("note"):
            lines.append(f"- Note: {OWNER_SUPPLIES[name]['note']}")
        sheet = out / f"{name}.md"
        atomic_write(sheet, "\n".join(lines) + "\n")
        sheets.append(sheet)
    return sheets


def build_owner_checklist() -> Path:
    lines = [
        "# OWNER-SUPPLY CHECKLIST — BIOS / keys / firmware",
        "",
        "These are **yours to provide** — personally dumped, never downloaded",
        "by automation, never staged in this repo, never hashed into records.",
        "",
        "## Per-emulator requirements",
        "",
    ]
    for app, info in OWNER_SUPPLIES.items():
        lines.append(f"### {app}")
        lines.append(f"- Where it goes: `{info['dest']}`")
        if info["files"]:
            for f in info["files"]:
                lines.append(f"- [ ] {f}")
        else:
            lines.append("- [x] Nothing needed")
        if info.get("note"):
            lines.append(f"  - {info['note']}")
        lines.append("")
    lines += [
        "## Rules",
        "",
        "- Only dump BIOS/keys/firmware from hardware/software you own.",
        "- Automation never copies these files; you place them via the app's",
        "  picker (Eden, Cemu) or by copying into the BIOS folder yourself.",
        "- These files are excluded from git, from records, and from logs.",
        "- If you switch devices later, re-dump rather than reusing across devices",
        "  where the emulator warns about it.",
    ]
    p = KIT / "OWNER-SUPPLY-CHECKLIST.md"
    atomic_write(p, "\n".join(lines) + "\n")
    return p


def build_storage_variants_md(variants: dict) -> Path:
    lines = [
        "# STORAGE CHOICE — pick before transfer day",
        "",
        "Four supported variants. Profile paths stay `${ROM_ROOT}`; the",
        "`thorctl storage bind` step records which you chose.",
        "",
    ]
    for key, v in variants.items():
        lines += [
            f"## {v['label']}  (`{key}`)",
            "",
            f"- ROM root looks like: `{v['rom_root_discovered']}`",
            f"- Pros: {v['pros']}",
            f"- Cons: {v['cons']}",
            f"- Transfer: {v['transfer_path']}",
            f"- Notes: {v['notes']}",
            "",
        ]
    lines += ["**Recommended default:** hybrid_sd_internal for large Switch/3DS",
              "libraries; plain sd_card if you value re-seat-ability and simplicity."]
    p = KIT / "STORAGE-VARIANTS.md"
    atomic_write(p, "\n".join(lines) + "\n")
    return p


def build_kit_manifest(profile: dict, storage_variants: dict) -> dict:
    manifest = {
        "schema_version": 1,
        "kit": "ayn-thor-offline-kit",
        "generated_at_utc": __import__("lib_thor").utc(),
        "apks": {},
        "drivers": {},
        "staged_configs": {},
        "library_manifest": None,
        "owner_supplies": {k: v["files"] for k, v in OWNER_SUPPLIES.items()},
        "storage_variants": list(storage_variants.keys()),
    }
    for apk in sorted(APKS.glob("*.apk")):
        manifest["apks"][apk.name] = kit_hash(apk)
    for d in sorted(DRIVERS.glob("*")):
        if d.is_file() and not d.name.endswith(".lock.json"):
            manifest["drivers"][d.name] = kit_hash(d)
    for cfg in sorted((STAGING).glob("*.cfg")) + sorted((STAGING).glob("*.json")):
        manifest["staged_configs"][cfg.name] = kit_hash(cfg)
    lm = LIBRARY / "canonical-ssd-manifest.json"
    if lm.exists():
        m = json.loads(lm.read_text())
        manifest["library_manifest"] = {
            "path": str(lm.relative_to(ROOT)),
            "file_count": m.get("file_count"),
            "total_size_bytes": m.get("total_size_bytes"),
            "sha256": kit_hash(lm)["sha256"],
        }
    return manifest


def main() -> int:
    profile = json.loads(PROFILE.read_text())
    variants = json.loads((ROOT / "configs" / "storage-variants.json").read_text())
    KIT.mkdir(parents=True, exist_ok=True)

    sheets = build_apply_sheets(profile)
    owner = build_owner_checklist()
    storage_md = build_storage_variants_md(variants["storage_variants"])
    manifest = build_kit_manifest(profile, variants["storage_variants"])
    atomic_write(KIT / "kit-manifest.json",
                 json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"offline kit built: {KIT.relative_to(ROOT)}/")
    print(f"  apply-sheets:    {len(sheets)} emulators")
    print(f"  apks staged:     {len(manifest['apks'])}")
    print(f"  drivers staged:  {len(manifest['drivers'])}")
    print(f"  configs staged:  {len(manifest['staged_configs'])}")
    lm = manifest.get("library_manifest")
    print(f"  library:         {lm['file_count'] if lm else 0} files"
          f" ({round(lm['total_size_bytes']/1e9,1) if lm else 0} GB)")
    print(f"  storage options: {len(variants['storage_variants'])} variants")
    print(f"  owner supplies:  checklist at {owner.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
