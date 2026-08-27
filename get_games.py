#!/usr/bin/env python3
"""Download games from the Homebrew Hub (hh3.gbdev.io) — 100% free/legal homebrew
for GB / GBC / GBA / NES — straight into your ROMs folder structure.

Usage:
  python3 get_games.py                     # curated preset into ./sd_card/ROMs/
  python3 get_games.py /Volumes/YOUR_SD    # onto a mounted SD card
  python3 get_games.py --auto 5            # + 5 random games per platform
  python3 get_games.py --list              # show what's in the preset
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
API = "https://hh3.gbdev.io/api"
UA = {"User-Agent": "ayn-automation/1.0"}

FOLDERS = {"GB": "gb", "GBC": "gbc", "GBA": "gba", "NES": "nes"}

# hand-picked quality homebrew (slug -> why)
PRESET = {
    # Game Boy
    "libbet":        "puzzle-platformer (pinobatch)",
    "tobutobugirl":  "arcade platformer",
    "2048gb":        "2048 puzzle",
    "deadeus":       "horror visual novel",
    # Game Boy Color
    "ucity":         "city builder",
    "petris":        "falling-block puzzle",
    # Game Boy Advance
    "basil-termini_2048-advance": "2048 Advance",
    "origamiscienceguy_galactic-quest": "space shooter RPG",
    "jeremyelkayam_trogba": "Trogdor!",
    "bloxorz-gba":   "3D block puzzle",
    # NES
    "johnybot_tiny-golf": "minigolf",
    "johnybot_kart-racer": "kart racer",
}

def fetch_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def rom_url(entry: dict) -> str | None:
    """Resolve exact ROM URL from the game page payload (paths vary per entry)."""
    fname = rom_filename(entry)
    if not fname:
        return None
    try:
        req = urllib.request.Request(f"https://hh.gbdev.io/game/{entry['slug']}", headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", "ignore")
        m = re.search(rf'https://hh3\.gbdev\.io/static/[^"\\]+/{re.escape(fname)}', html)
        return m.group(0).replace("\\/", "/") if m else None
    except Exception:
        return None

def rom_filename(entry: dict) -> str | None:
    playable = [f["filename"] for f in entry.get("files", []) if f.get("playable")]
    if not playable:
        return None
    return sorted(playable, key=lambda f: ("web" in f.lower(), len(f)))[0]

def download(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"= {dest.name} (cached)")
        return True
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            dest.write_bytes(r.read())
        print(f"✓ {dest.parent.name}/{dest.name} ({dest.stat().st_size/1024:.0f} KB)")
        return True
    except Exception as e:
        print(f"✗ {url}: {e}")
        return False

def rom_target(roms_dir: Path, entry: dict) -> Path | None:
    plat = FOLDERS.get(entry.get("platform"))
    if not plat:
        return None
    fname_full = rom_filename(entry)
    if not fname_full:
        return None
    out = roms_dir / plat / Path(fname_full).name
    out.parent.mkdir(parents=True, exist_ok=True)
    return out

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default=str(ROOT / "sd_card"))
    ap.add_argument("--auto", type=int, metavar="N", help="also grab N random games per platform")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    roms_dir = Path(args.target).expanduser() / "ROMs"
    ok = fail = 0

    if args.list:
        for slug, note in PRESET.items():
            print(f"{slug:40s} {note}")
        return 0

    entries = {}
    for slug in PRESET:
        try:
            e = fetch_json(f"{API}/entry/{urllib.parse.quote(slug)}.json")
            entries[slug] = e
        except Exception as ex:
            print(f"✗ lookup {slug}: {ex}")

    if args.auto:
        for plat in FOLDERS.values():
            q = urllib.parse.urlencode({"platform": plat.upper(), "typetag": "game", "random": "true"})
            try:
                data = fetch_json(f"{API}/search?{q}")
                for e in data.get("entries", [])[: args.auto]:
                    entries.setdefault(e["slug"], e)
            except Exception as ex:
                print(f"✗ search {plat}: {ex}")

    for slug, e in entries.items():
        dest = rom_target(roms_dir, e)
        if not dest:
            continue
        url = rom_url(e)
        if not url:
            print(f"✗ {slug}: no ROM URL found")
            fail += 1
            continue
        if download(url, dest):
            ok += 1
        else:
            fail += 1

    print(f"\n{ok} games ready, {fail} failed → {roms_dir}")
    return 1 if fail else 0

if __name__ == "__main__":
    sys.exit(main())
