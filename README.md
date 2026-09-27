# ayn-automation

Preparation toolkit for AYN Thor-style Android emulation handhelds: downloads
and stages reviewed emulator assets, builds a ROM layout, and produces
configuration and acceptance materials. It does **not** deploy to a real device
until a verified explicit-serial deployment adapter exists.

## Goal

Make an AYN Thor feel like a console: keep an owned game library in one
platform-based `ROMs/` tree, configure the emulators behind it, and present
the result through a fast, artwork-rich Cocoon home screen.

## Quick start

1. Run `./setup_all.sh --no-deploy` on a Mac to stage apps, a safe ROM layout,
   homebrew, and emulator configuration.
2. Add your own legally obtained games with `./add_games.sh ~/my-roms`.
3. On the Thor, select `Internal storage/ROMs` in Cocoon, enable Smart Folders,
   then scrape artwork.
4. Use the first-device acceptance checklist before setting Cocoon as the
   default launcher.

For the intended console-style visual setup, read
[the frontend design guide](docs/FRONTEND-DESIGN.md). The project never
distributes copyrighted games, console BIOS files, firmware, or title keys.

## Prepare on your Mac

```zsh
./setup_all.sh --no-deploy     # apps + SD layout + legal homebrew + configs
./setup_all.sh --no-deploy --auto-games 5  # also grab 5 random homebrew/platform
```

## Growing your library

```zsh
./add_games.sh ~/my-roms           # stage your own ROMs by extension → sd_card/ROMs/<system>
./add_games.sh ~/my-roms --push    # …and sync straight to the connected device
SD=/Volumes/YOUR_SD ./add_games.sh ~/my-roms   # or target a mounted card
```

Game files are copyrighted — bring your own collection; the built-in preset
(`get_games.py`) only pulls free homebrew from the Homebrew Hub (hh3.gbdev.io).

## Individual pieces

| script | what it does |
|---|---|
| `apps.py` | resolves latest APKs from RJNY dual-screen Obtainium pack into `apks/`; `--optional Citra,DraStic-Rev,PPSSPP-Dual,Console Launcher` for the written-guide extras |
| `prepare_sd.py [target] --zip-nds` | ES-DE folder structure + BIOS checklist; `--zip-nds` compresses .nds→.zip per the guide |
| `get_games.py [--auto N]` | curated legal homebrew preset (+N random/platform) into `sd_card/ROMs/` |
| `make_retroarch_cfg.py` | retroarch.cfg with the guide's settings |
| `deploy.sh` | **disabled legacy script**; it must not be used for device deployment |
| `probe.py <serial>` | 9-point capability probe, cached per device (v2 §6) |
| `golden.py <serial> capture\|restore` | golden-image capture/restore w/ credential scrub + UUID path rewrite |
| `lib_thor.py` | lockfile/debounce/logging/backups/verified adb primitives |
| `thor_library.py scan\|sync\|verify` | read-only canonical SSD manifest, human listing, and hash-verified incremental staging sync (dry-run by default) |
| `emulator_profiles.py validate\|plan` | validates the versioned AYN Thor emulator profile and emits a no-device-safe deployment/acceptance plan |
| `GUIDE-NOTES.md` | deltas from the Apr-2026 written guide (formats, settings, optional apps) |
| `transcribe.sh <url-or-file>` | bulk YouTube → accurate Whisper transcripts (MLX) |

State lives in `~/.thor-provision/` (capabilities.json, state.json, logs/, golden/, backups/).

## Canonical SSD library

The mounted SSD is the authoritative game library. Build an auditable manifest
and preview staging changes without writing any game files:

```zsh
python3 thor_library.py sync
```

This reads `/Volumes/Extreme SSD/ayn-thor-card/ROMs`, writes a JSON manifest,
human directory listing, and structured sync report to `library/`, and plans
the changes needed for `sd_card/ROMs`. It excludes `BIOS`, `_extras`, ES-DE
`systeminfo.txt`, hidden files, symlinks, unknown support assets, ROM-root
files, and nested assets. A game must be a direct child of its platform folder.
`.zip` is retained only when it is in such a platform folder, because many
emulators read compressed ROMs directly; it is not extracted or trusted as an
installer by this sync layer. Archive inspection/extraction belongs to the
separate ingestion workflow. It never deletes SSD or staging files.

After reviewing `library/sync-report.json`, apply only the required copies:

```zsh
python3 thor_library.py sync --apply
python3 thor_library.py verify
```

Copies are resumable via tool-owned partial files, SHA-256 verified, and
atomically placed. A changed managed game in staging is replaced only with
`--apply`; unmanaged extras are left alone.


## Device notes (learned while testing)

- Azahar's package id is `io.github.lime3ds.android`; Eden ships disguised as
  `com.miHoYo.Yuanshen`. Both install fine — don't be alarmed.
- `adb push sd_card/ROMs /sdcard/` (no trailing slash!) — otherwise you nest ROMs/ROMs.
- Real Thor: enable Developer Options + USB debugging, then run `./deploy.sh`.
- Manual one-time steps after deploy are printed at the end of deploy.sh
  (per-emulator wizards, Cocoon credentials, scraping).

## Emulator profile and first device

`profiles/ayn-thor-v1.json` captures the emulator-specific recommendations from
the local AYN Thor starter-guide transcript: Cocoon mappings, RetroArch cores/
BIOS/Vulkan/hotkeys, dual-screen defaults for Azahar and melonDS, Eden's
keys/firmware/driver/update checks, and paths/settings for Dolphin, Cemu,
DuckStation, NetherSX2, and PPSSPP. It does **not** pretend these can safely be
written before the actual device and installed app versions are known.

```zsh
python3 emulator_profiles.py validate
python3 emulator_profiles.py plan --serial YOUR_SERIAL --rom-root /SAF-selected-or-device-discovered/ROMs
```

The plan is deliberately non-authorizing even if its capability data is forged:
it cannot install, push, or change a device. `deploy.sh` is disabled until a
replacement binds a verified live preflight to the explicit device serial.

See `docs/AYN-THOR-FIRST-DEVICE-ACCEPTANCE.md` for the first-device checklist.
The planner and the checklist are the only supported route for a new Thor;
`deploy.sh` is intentionally disabled.

## Emulator-as-test-device

```zsh
export JAVA_HOME=/opt/homebrew/opt/openjdk ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
avdmanager create avd -n thor-test -k "system-images;android-35;google_apis;arm64-v8a"
emulator -avd thor-test -gpu swiftshader_indirect &
```

## Transcripts

`transcripts/AYN-Thor-Starter-Guide [lNfo6MkyPpk].txt` — source guide this
automation mirrors (Russ @ MetroGameCore).
