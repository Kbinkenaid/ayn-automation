#!/usr/bin/env python3
"""Download legal PSP homebrew games (GitHub releases) into the PSP ROMs folder.

Each game lands as ROMs/psp/<Name>/EBOOT.PBP — the layout PPSSPP expects when
scanning the PSP directory.

Usage: python3 get_psp_homebrew.py [target]     # default ./sd_card
"""
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
UA = {"User-Agent": "ayn-automation/1.0"}

# repo -> asset name filter
GAMES = {
    "kevinbchen/cspsp":                 ("cspsp", "CSPSP — Counter-Strike-like shooter"),
    "kwerenta/joker-poker":             ("joker-poker.zip", "Joker Poker — Balatro-inspired"),
    "JeffRuLz/OpenHCL":                 ("OpenHCL_PSP", "Hydra Castle Labyrinth — metroidvania"),
    "dbeef/spelunky-psp":               (".pbp", "Spelunky PSP remake"),
}

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()

def install(repo: str, psp_dir: Path, name_hint: str) -> bool:
    dest_root = psp_dir / name_hint.split(" — ")[0].replace(" ", "_")
    marker = dest_root / ".installed"
    if marker.exists():
        print(f"= {name_hint} (cached)")
        return True
    try:
        rel = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest"))
        assets = [a for a in rel.get("assets", []) if name_hint == "Spelunky PSP remake"
                  or any(x.lower() in a["name"].lower() for x in (".zip", ".pbp"))]
        # pick the right asset per game
        filt = GAMES[repo][0]
        assets = [a for a in assets if filt.lower() in a["name"].lower()]
        if not assets:
            print(f"✗ {repo}: no matching asset")
            return False
        data = fetch(assets[0]["browser_download_url"])
        dest_root.mkdir(parents=True, exist_ok=True)
        if assets[0]["name"].lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                z.extractall(dest_root)
            # flatten single wrapper dir so EBOOT.PBP sits directly under <game>/
            entries = list(dest_root.iterdir())
            eboot = next(dest_root.rglob("EBOOT.PBP"), None)
            if eboot and eboot.parent != dest_root:
                for f in eboot.parent.iterdir():
                    shutil.move(str(f), dest_root / f.name)
                extra = eboot.parent
                shutil.rmtree(extra, ignore_errors=True)
        else:  # bare .pbp
            (dest_root / "EBOOT.PBP").write_bytes(data)
        if not list(dest_root.rglob("EBOOT.PBP")):
            print(f"✗ {repo}: no EBOOT.PBP after extract")
            return False
        marker.write_text(rel.get("tag_name", ""))
        size = sum(f.stat().st_size for f in dest_root.rglob("*") if f.is_file())
        print(f"✓ {dest_root.name} ({size/1024:.0f} KB)")
        return True
    except Exception as e:
        print(f"✗ {repo}: {e}")
        return False

def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "sd_card"
    psp_dir = target.expanduser() / "ROMs" / "psp"
    psp_dir.mkdir(parents=True, exist_ok=True)
    ok = sum(install(repo, psp_dir, hint) for repo, (_, hint) in GAMES.items())
    print(f"\n{ok}/{len(GAMES)} PSP homebrew games ready → {psp_dir}")
    return 0 if ok == len(GAMES) else 1

import shutil

if __name__ == "__main__":
    sys.exit(main())
