#!/usr/bin/env python3
"""Resolve + download the latest APKs for the AYN Thor setup (RJNY dual-screen pack).

Sources of truth: vendor/emulation-pack-dual-screen.json (from RJNY releases).
GitHub-sourced apps resolve via the GitHub API; special resolvers handle
Eden / RetroArch buildbot. Non-GitHub web sources fall back to HTML scraping.

Usage:
  python3 apps.py                 # download curated default set into apks/
  python3 apps.py --list          # show every app in the pack
  python3 apps.py --only Azahar,Cocoon   # subset by name substring
  python3 apps.py --all           # everything in the pack (incl. track-only skipped)
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
VENDOR = ROOT / "vendor"
APKS = ROOT / "apks"
PACK_JSON = VENDOR / "emulation-pack-dual-screen.json"
UA = {"User-Agent": "ayn-automation/1.0"}

# The video's curated install list (name -> match key in pack JSON)
DEFAULT_APPS = [
    "Azahar", "Cemu", "Dolphin Emulator", "DuckStation", "Eden",
    "WatermelonDS", "NetherSX2", "PPSSPP", "RetroArch (AArch64)",
    "Cocoon FE", "GameNative", "Artemis", "Pixel Guide Android", "Flycast",
    "MelonDS",
]

# from the written guide (retrogamecorps.com 2026-04 update) — not all in the pack
OPTIONAL_APPS = {
    # guide: use the Storage Access Antutu variant of Citra MMJ
    "Citra": {"match": "Citra", "note": "3DS perf alternative; Storage Access Antutu build"},
    # guide: DraStic is abandoned upstream; this fork restores Thor touch input
    "DraStic-Rev": {"repo": "https://github.com/R-YaTian/DraStic_rev_i18n",
                    "note": "DS; Thor bottom-screen touch + shaders"},
    # guide: experimental dual-screen PPSSPP (zoom second screen, e.g. minimap)
    "PPSSPP-Dual": {"repo": "https://github.com/SapphireRhodonite/ppsspp",
                    "note": "PSP experimental dual-screen"},
    "Console Launcher": {"match": "Console Launcher",
                         "note": "frontend with new dual-screen beta support"},
}

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def gh_latest_apk(repo_url: str) -> tuple[str, str]:
    """Return (version_or_tag, apk_url) for latest GitHub release asset."""
    repo = repo_url.rstrip("/").replace("https://github.com/", "")
    data = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases/latest"))
    tag, assets = data.get("tag_name", "?"), data.get("assets", [])
    apks = [a for a in assets if a["name"].lower().endswith(".apk")]
    if not apks:
        raise RuntimeError(f"no .apk in {repo} release {tag}")
    def score(a):
        n = a["name"].lower()
        s = 0
        if "arm64" in n: s += 4
        if "universal" in n: s += 2
        if "gold" in n and "ppsspp" in repo.lower(): s -= 1  # prefer free over gold? keep gold ok
        if "aarch64" in n: s += 4
        return -s
    apks.sort(key=score)
    return tag, apks[0]["browser_download_url"]

def resolve(app: dict) -> tuple[str, str]:
    url = app["url"]
    settings = json.loads(app.get("additionalSettings") or "{}")
    if settings.get("trackOnly"):
        return None
    # manual overrides for bot-protected sites (refresh via webfetch)
    ov_file = VENDOR / "overrides.json"
    if ov_file.exists():
        ov = json.loads(ov_file.read_text())
        if app["name"] in ov:
            return "override", ov[app["name"]]
    if "github.com" in url:
        return gh_latest_apk(url)
    if "eden-emu.dev" in url:  # GitHub-style release JSON, assets = list of URLs
        meta = json.loads(fetch(url))
        apks = [a for a in meta.get("assets", []) if isinstance(a, str) and a.endswith(".apk")]
        if not apks:
            raise RuntimeError("no eden apk in release.json")
        apks.sort(key=lambda u: ("optimized" not in u, "chromeos" in u))
        return meta.get("tag_name", "latest"), apks[0]
    if "buildbot.libretro.com" in url:  # stable listing -> version dir -> aarch64 apk
        html = fetch("https://buildbot.libretro.com/stable/").decode()
        versions = sorted(set(re.findall(r'href="/stable/(\d+\.\d+\.\d+)/"', html)),
                          key=lambda v: [int(x) for x in v.split(".")])
        ver = versions[-1]
        return ver, f"https://buildbot.libretro.com/stable/{ver}/android/RetroArch_aarch64.apk"
    # generic scrape for .apk link on the page
    html = fetch(url).decode("utf-8", "ignore")
    m = re.search(r'href="([^"]+\.apk)"', html, re.I)
    if m:
        link = m.group(1)
        if link.startswith("/"):
            from urllib.parse import urlparse
            p = urlparse(url)
            link = f"{p.scheme}://{p.netloc}{link}"
        return "web", link
    raise RuntimeError(f"no resolver for {app['name']} ({url})")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated name substrings")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--optional", help="comma-separated optional names (see OPTIONAL_APPS)")
    ap.add_argument("--list-optional", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list_optional:
        for k, v in OPTIONAL_APPS.items():
            print(f"{k:20s} {v.get('note', '')}")
        return 0

    pack = json.loads(PACK_JSON.read_text())["apps"]
    if args.list:
        for a in pack:
            print(f"{a['name']:28s} {a['id']}")
        return 0
    if args.list:
        for a in pack:
            print(f"{a['name']:28s} {a['id']}")
        return 0

    keys = DEFAULT_APPS
    if args.only:
        keys = [k.strip() for k in args.only.split(",")]
    selected = []
    for key in keys:
        matches = [a for a in pack if key.lower() in a["name"].lower()]
        if not matches:
            print(f"WARN: '{key}' not in pack", file=sys.stderr)
        elif not args.all and key == "MelonDS" and any("watermelon" in m["name"].lower() or "dual" in m["name"].lower() for m in matches):
            pass
        selected.extend(matches[:1])
    if args.optional:
        for name in [k.strip() for k in args.optional.split(",")]:
            opt = OPTIONAL_APPS.get(name)
            if not opt:
                print(f"WARN: optional '{name}' unknown (--list-optional)", file=sys.stderr)
                continue
            if "repo" in opt:  # synthetic GitHub-sourced entry
                selected.append({"name": name, "id": "-", "url": opt["repo"],
                                 "additionalSettings": "{}"})
            else:
                m = [a for a in pack if opt["match"].lower() in a["name"].lower()]
                selected.extend(m[:1])
    if args.all:
        selected = pack

    APKS.mkdir(exist_ok=True)
    ok = fail = 0
    for app in selected:
        name = app["name"]
        try:
            tag, apk_url = resolve(app)
            dest = APKS / f"{re.sub(r'[^\w.-]+', '_', name)}-{tag}.apk"
            if dest.exists() and dest.stat().st_size > 0:
                print(f"= {name}: cached {dest.name}")
                ok += 1
                continue
            print(f"↓ {name} [{tag}] ...", flush=True)
            dest.write_bytes(fetch(apk_url))
            print(f"✓ {name}: {dest.stat().st_size/1e6:.1f} MB")
            ok += 1
        except Exception as e:
            print(f"✗ {name}: {e}", file=sys.stderr)
            fail += 1
    print(f"\n{ok} ready, {fail} failed → {APKS}")
    return 1 if fail else 0

if __name__ == "__main__":
    sys.exit(main())
