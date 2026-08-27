#!/usr/bin/env python3
"""Prepare a microSD card (or staging dir) exactly as the AYN Thor guide prescribes.

- Downloads retrogamecorps ES-DE-Directories ROMs.zip -> ROMS/<system> tree
  (compatible with Cocoon, ES-DE, Daijishō, etc.)
- Creates ROMS/BIOS/ with a checklist of every BIOS file the video requires
- Optionally copies YOUR OWN rom collection in (--roms-src, matched by folder name)

Usage:
  python3 prepare_sd.py /Volumes/YOUR_SD          # real card
  python3 prepare_sd.py                           # staging dir ./sd_card
  python3 prepare_sd.py /Volumes/SD --roms-src ~/Games/ROMs
"""
import argparse
import io
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
VENDOR = ROOT / "vendor"
UA = {"User-Agent": "ayn-automation/1.0"}

BIOS_CHECKLIST = """BIOS files — you must supply these yourself (copyrighted).
Place each file directly into this BIOS folder unless noted.

Nintendo
  gb_bios.bin        Game Boy      (optional — enables boot logo)
  gbc_bios.bin       Game Boy Color(optional — enables boot logo)
  gba_bios.bin       Game Boy Advance (required by some cores, e.g. mGBA)
  prod.keys          Switch keys   (must match firmware version; guide uses 9.0.1)
  firmware.zip       Switch firmware (same version as prod.keys)

Sony
  SCPH1001.bin etc.  PS1 (any valid region BIOS)
  rom1.bin rom2.bin erom1.bin erom2.bin  PS2 (example set)
Sega
  bios_*             Sega CD region BIOS
  mpr17933.bin       Saturn (JP)
  sega_101.bin       Saturn (US)
  dc/                Dreamcast: put dc_boot.bin + dc_flash.bin INSIDE this subfolder

Arcade
  neogeo.zip         Neo Geo BIOS — goes in your neogeo ROMS folder (not here)
"""

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def latest_roms_zip() -> Path:
    dest = VENDOR / "ROMs.zip"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    VENDOR.mkdir(exist_ok=True)
    data = json.loads(fetch("https://api.github.com/repos/retrogamecorps/ES-DE-Directories/releases/latest"))
    asset = next(a for a in data["assets"] if a["name"].lower().endswith(".zip"))
    print(f"↓ {asset['name']} ...")
    dest.write_bytes(fetch(asset["browser_download_url"]))
    return dest

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default=str(ROOT / "sd_card"),
                    help="SD mount point or staging dir (default ./sd_card)")
    ap.add_argument("--roms-src", help="folder of your own ROMs to copy in")
    ap.add_argument("--zip-nds", action="store_true",
                    help="compress loose .nds files to .zip (guide recommendation; "
                         "melonDualDS and DraStic read zips directly)")
    args = ap.parse_args()

    target = Path(args.target).expanduser()
    roms = target / "ROMs"
    roms.mkdir(parents=True, exist_ok=True)

    zipl = latest_roms_zip()
    with zipfile.ZipFile(zipl) as z:
        names = z.namelist()
        top = "ROMs" if any(n.startswith("ROMs/") for n in names) else ""
        count = 0
        for info in z.infolist():
            rel = info.filename[len(top):].lstrip("/") if top else info.filename
            if not rel or rel.startswith("__MACOSX"):
                continue
            out = roms / rel
            if info.is_dir():
                out.mkdir(parents=True, exist_ok=True)
            else:  # keep System Info text files, they document extensions
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(z.read(info))
            count += 1

    bios = roms / "BIOS"
    bios.mkdir(exist_ok=True)
    (bios / "dc").mkdir(exist_ok=True)          # Dreamcast needs its own subfolder
    (bios / "BIOS-CHECKLIST.txt").write_text(BIOS_CHECKLIST)
    (target / "cocoon").mkdir(exist_ok=True)     # Cocoon data dir (per video)

    copied = ""
    if args.roms_src:
        src = Path(args.roms_src).expanduser()
        if src.is_dir():
            for child in src.iterdir():
                if child.is_dir():
                    shutil.copytree(child, roms / child.name, dirs_exist_ok=True)
            copied = f" + your ROMs from {src}"

    if args.zip_nds:
        import zipfile as zf
        nds = roms / "nds"
        if nds.is_dir():
            zipped = 0
            for f in list(nds.glob("*.nds")):
                out = f.with_suffix(".zip")
                if out.exists():
                    continue
                with zf.ZipFile(out, "w", zf.ZIP_DEFLATED) as z:
                    z.write(f, arcname=f.name)
                f.unlink()
                zipped += 1
            copied += f" [{zipped} .nds -> .zip]"

    systems = len([p for p in roms.iterdir() if p.is_dir()])
    print(f"✓ {roms} ready ({systems} system folders, {count} files){copied}")
    print(f"✓ BIOS folder + checklist at {bios}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
