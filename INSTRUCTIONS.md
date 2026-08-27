# External SSD — Thor Library Instructions

SSD location:  `/Volumes/Extreme SSD/ayn-thor-card/`
This folder is an exact clone of what the microSD card should contain.

```
ayn-thor-card/
├── ROMs/                  ← ALL games live here, one folder per system
│   ├── n3ds/              ← Nintendo 3DS   (.3ds / .cci — decrypted dumps)
│   ├── nds/               ← Nintendo DS    (.nds or .zip)
│   ├── psp/               ← PSP UMD rips   (.iso / .cso) + homebrew folders w/ EBOOT.PBP
│   ├── psx/  ps2/         ← PlayStation 1 (.bin+.cue/.chd) / PS2 (.iso/.chd)
│   ├── gc/   wii/         ← GameCube / Wii (.rvz / .iso / .wbfs)
│   ├── wiiu/              ← Wii U          (.wua)
│   ├── gb/ gbc/ gba/      ← Game Boy family
│   ├── nes/ snes/ n64/ genesis/ saturn/ dreamcast/ arcade/ neogeo/
│   ├── switch/            ← Switch         (.xci / .nsp)
│   ├── steam/             ← GameNative shortcuts
│   ├── BIOS/              ← system BIOS files (read BIOS-CHECKLIST.txt inside)
│   └── <179 more>         ← full ES-DE list; each has systeminfo.txt with accepted types
├── cocoon/                ← Cocoon frontend data dir (artwork after scraping)
├── retroarch.cfg          ← pre-configured RetroArch settings
└── ingest-manifest.json   ← log of every ingested file + SHA-256 hashes
```

## HOW TO ADD GAMES (the only command you need)

Drop your dump files anywhere first (Downloads, a USB stick, wherever), then:

```zsh
cd "/Volumes/Extreme SSD"        # if your scripts live elsewhere adjust path
python3 ~/Desktop/Projects/ayn-automation/ingest_library.py <folder-with-files>
```

That command is a **dry-run**: it recursively considers files but never copies
folders, `.txt`, or `.md` metadata. It writes an auditable
`ingest-manifest.json`. Review it, add a decision for every `needs_review`
disc image, then use `--apply`:

```zsh
python3 ~/Desktop/Projects/ayn-automation/ingest_library.py <folder-with-files> \
  --decisions my-platform-decisions.json --apply
```

For an archive containing a base game and an update, select one exact,
top-level member—archives with multiple playable members never auto-extract:

```json
{
  "schema_version": 1,
  "archive_members": {
    "My collection.zip": {"member": "Base Game.iso", "platform": "ps2"}
  }
}
```

The intake workflow:

1. rejects unsafe archive paths, symlinks, executables, duplicate names, and
   archives over its count/expanded-size limits before extraction;
2. maps unique formats (for example `.nsp`/`.xci` → `switch`, `.wbfs` →
   `wii`, `.wua` → `wiiu`);
3. holds `.iso`, `.rvz`, `.bin`, `.cue`, `.chd`, and `.m3u` for review unless a known
   platform folder or your decision file resolves them;
4. copies only approved files, hash-verifies them, and records the result.

Then delete your loose originals — nothing needs to stay on the Mac.

## MANUAL MOVING (if you'd rather drag-and-drop)

Match by extension — the folder name always matches the file type:

| Your file ends in | Move into |
|---|---|
| .3ds / .cci | ROMs/n3ds |
| .nds | ROMs/nds |
| .cso | ROMs/psp |
| .iso / .bin / .cue / .chd | Decide platform first — these formats are ambiguous |
| .iso from a DVD drive rip of PS2 | ROMs/ps2 |
| .wbfs | ROMs/wii |
| .rvz | Decide GameCube vs Wii first |
| .wua | ROMs/wiiu |
| .nsp / .xci | ROMs/switch |
| .gb / .gbc / .gba | ROMs/gb, gbc, gba |
| .nes / .sfc | ROMs/nes, snes |
| .z64 | ROMs/n64 |
| .md | ROMs/genesis |

Unsure? Open `ROMs/<system>/systeminfo.txt` — it lists exactly which
extensions belong there.

## WHEN THE THOR ARRIVES

Either clone this whole tree onto the microSD card (card reader), or:
```zsh
cd ~/Desktop/Projects/ayn-automation && ./deploy.sh     # pushes over USB
```
