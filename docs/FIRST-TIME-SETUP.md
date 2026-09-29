# First-Time Setup Guide — AYN Thor (beginner-friendly)

Everything below is in the order you'll actually do it. Steps marked **[AUTO]**
are run on your Mac with `thorctl`; steps marked **[DEVICE]** are taps on the
Thor. Nothing installs a driver, key, BIOS, or credential for you — those stay
manual by design.

---

## Part 0 — Before the Thor arrives (Mac, 15 min)

**[AUTO] 1. Scan your game library** (SSD with your ROMs mounted):

```bash
cd ~/Desktop/Projects/ayn-automation
python3 thorctl.py library scan
python3 thorctl.py library sync --apply    # copies reviewed games into staging
python3 thorctl.py library verify          # proves every hash matches
```

**[AUTO] 2. Validate the emulator profile:**

```bash
python3 thorctl.py profile validate        # should print: "valid", 11 emulators
```

Everything (APKs and public metadata) is staged in `apks/` and
`vendor/drivers/`. Owner-supplied BIOS, keys, firmware, games, and GPU-driver
archives stay outside this repository.

---

## Part 1 — First connection (10 min)

**[DEVICE] 1.** Settings → About → tap Build Number 7× → Developer Options →
enable **USB debugging**. Plug the Thor into the Mac.

**[DEVICE] 2.** Accept the "Allow USB debugging?" prompt on the Thor.

**[AUTO] 3.** Find your serial (only device plugged in):

```bash
adb devices        # note the serial, e.g. 1A2B3C4D5E
```

**[AUTO] 4.** Introduce the device to thorctl (identity + capability probe):

```bash
python3 thorctl.py device discover --serial YOUR_SERIAL
python3 thorctl.py device probe    --serial YOUR_SERIAL --refresh
```

---

## Part 2 — Storage & plan (5 min)

**[AUTO] 1.** Pick where games live. Recommended: the micro-SD card.
On the Thor, open Files and note the card path (looks like
`/storage/XXXX-XXXX/`), then:

```bash
python3 thorctl.py storage bind --serial YOUR_SERIAL \
    --rom-root /storage/XXXX-XXXX/ROMs --storage-type removable
```

**[AUTO] 2.** Generate the deployment plan and read it:

```bash
python3 thorctl.py deployment plan
```

The plan lists every app, every game, and every manual task. Nothing has been
installed yet — the plan is a review document.

---

## Part 3 — Install emulators (20 min)

**[AUTO] 1.** Push the staged APKs to the device and install them
(via thorctl transfer/apply once Phase 2+ is built; for now, adb install the
pinned files — they are hash-verified in `~/.thor-provision/thorctl-records/`):

```bash
for apk in apks/RetroArch_AArch64_-1.22.2.apk apks/Azahar-2126.0.apk \
           apks/AzaharPlus-2126.0-A-coexists.apk apks/WatermelonDS-0.7.0.apk \
           apks/CemuDS-0.5.2.apk apks/Cemu-0.5.2.apk apks/Dolphin_Emulator-override.apk \
           apks/DuckStation-web.apk apks/NetherSX2-2.2n.apk apks/PPSSPP-web.apk \
           apks/Eden-v0.2.1.apk apks/Flycast-v2.7.apk apks/DraStic-Rev-rev260701.apk \
           apks/Cocoon_FE-beta-3.04.apk apks/ES-DE-Companion-v1.0.5.apk; do
  adb -s YOUR_SERIAL install -r "$apk"
done
```

> **ES-DE itself is a paid app** — buy it on Patreon (or Samsung/Huawei store),
> install the APK it gives you. The free Companion app is already staged.

---

## Part 4 — GPU driver: Apex v2 Ultimate (5 min, biggest Switch fix)

**[DEVICE] 1.** Obtain the owner-supplied
`Balemuni_Apex_v2_ULTIMATE_SD8Gen2.zip` archive. It targets the Thor's
QCS8550/Adreno 740 class. Do not substitute a Universal, Mali, or unrelated
Snapdragon package.

**[DEVICE] 2.** **Eden**: Settings → GPU Driver Manager → Install → select the
ZIP from `Download/` → select **Apex v2 Ultimate SD8 Gen 2** as active → restart
Eden. The first boot can spend longer compiling shaders.

**[DEVICE] 3.** Use the same archive in Dolphin's custom GPU-driver manager
only if Dolphin needs it; keep the system driver as the fallback.

**[AUTO] 4.** Record it in the audit chain:

```bash
python3 thorctl.py driver attest --emulator eden \
  --driver-name "Balemuni Apex v2 Ultimate SD8Gen2" \
  --driver-version "Apex-v2" \
  --source "manual: Eden GPU driver manager" \
  --fingerprint "<fingerprint shown by device discover>"
```

---

## Part 5 — Per-emulator setup (the manual pass, 60–90 min)

Work top to bottom. Full settings live in `profiles/ayn-thor-v1.json`.

| # | App | Key steps |
|---|---|---|
| 1 | **RetroArch** | Import `sd_card/retroarch.cfg`, BIOS folder → `ROMs/BIOS`, Vulkan driver, download the cores listed in the profile, verify hotkeys |
| 2 | **WatermelonDS** (DS) | Point at `ROMs/nds`, OpenGL renderer, 4x, dual preset (internal top / external bottom), test touch |
| 3 | **Azahar / AzaharPlus** (3DS) | SAF folders, Vulkan, 4x, top/bottom dual layout, Disable Right Eye Render |
| 4 | **Eden** (Switch) | Import *your* keys and firmware through Eden's first-run wizard, add the ROM folder, use Vulkan and docked mode |
| 5 | **CemuDS** (Wii U) | Game folder, keys via app, gamepad screen on bottom, per-game graphics packs |
| 6 | **DuckStation** (PS1) | Your BIOS, 3x, CRT-Lottes shader, run-ahead 1 frame |
| 7 | **NetherSX2** (PS2) | Your BIOS, OpenGL 2.5x, widescreen patches, verify physical controls |
| 8 | **Dolphin** (GC/Wii) | SAF folders, OpenGL 3x, compile shaders before play |
| 9 | **PPSSPP** (PSP) | Data + games folders, 4x |

### BIOS and PS3 firmware (owner-supplied)

Keep BIOS and console firmware in device-only storage. Never add the files to
this repository or place them in a public release.

| System | Emulator | Device setup |
|---|---|---|
| PS2 | NetherSX2 | Import a personally dumped PS2 BIOS in NetherSX2's BIOS picker; keep games in `ROMs/ps2`. One USA or Europe BIOS is normally enough; select another region only when a title requires it. |
| PS3 | aPS3e | Install the personally obtained official `PS3UPDAT.PUP` through **Install Firmware**, then point the game directory at `ROMs/ps3`. PS3 ISOs must be compatible/decrypted for aPS3e. |
| Switch | Eden | Import `prod.keys`, optional `title.keys`, and the extracted firmware dump through Eden's setup wizard; keep them in `Switch/keys/` and `Switch/firmware/<version>/`. |

The Thor validation completed with PS2 BIOS import, PS3 firmware installation,
and Switch keys/firmware available. These are setup facts only; no BIOS,
firmware, keys, ROM, or app-private data is tracked here.

### Eden (Switch): first-run order

Keep these three things separate:

| Item | Purpose | Recommended Thor location |
|---|---|---|
| `prod.keys` and optional `title.keys` | Lets Eden decrypt owned game content | `Internal storage/Switch/keys/` |
| Firmware dump (`.nca` files) | Supplies Switch system titles and applets | `Internal storage/Switch/firmware/<version>/` |
| Base games (`.xci` or `.nsp`) | The games Eden displays and launches | `Internal storage/ROMs/switch/` |

1. Open Eden and finish **Setup Emulator Data**. Choose **Keys**, then select
   `prod.keys` (and `title.keys` when offered) from `Switch/keys`.
2. Choose **Firmware**, select the folder containing the extracted `.nca` files
   from `Switch/firmware/<version>/`, and wait for the success message.
3. Choose **Games** and grant scoped access to `ROMs/switch` with **Use this
   folder** then **Allow**. Do not choose the whole Internal storage root.
4. In Eden settings, use **Vulkan**, leave accuracy at its default until a game
   needs a per-game adjustment, and enable docked mode for TV-style titles.
5. Restart Eden. The game grid should show base games. Install updates and DLC
   through Eden's content installer; do not launch update/DLC `.nsp` files as
   standalone games.

Eden must complete this wizard even if keys or firmware were copied to Android
app storage during troubleshooting. The wizard records the app's own storage
permission and setup state. Never publish, share, or commit keys, firmware,
BIOS files, game images, or any emulator data directory.

---

## Part 6 — Make it beautiful (the decoration pass, 20 min)

All inside **Cocoon** (and ES-DE):

**Cocoon 3 — Silk Pod themes:**
1. Cocoon → **Silk Pod** (in-app store) → browse themes
   (community favorites: PhantomOS, FloatUI, Persona-Wii, BotW, Balatro)
2. Themes are **modular** — mix wallpapers from one, icons from another,
   sounds from a third
3. Optional: Settings → Personalization → **Surface Material: Glass** →
   tune blur/refraction/tint (experimental, very pretty)
4. **Start → Edit Grid** → press **Y** on a tile to resize it; add
   **ThemePlaza badges** as image widgets
5. Scrape art: Settings → Scrape → priority **SteamGridDB → LaunchBox → IGDB
   → ScreenScraper**; the live preview lets you fix bad matches instantly
6. Check the info screen: reposition the logo over the hero art if it overlaps

**ES-DE (after buying it):**
1. Point it at the same ROM root
2. UI Themes downloader → install **Slate** (best maintained)
3. In Cocoon: enable **ES-DE linking** so artwork stays in sync between both

**Verification gate:** box art + themes render on **both screens** before you
set Cocoon as Home.

---

## Part 7 — Acceptance (one game per platform, 30 min)

For each platform, launch one game you own and verify: controls, save/load,
exit hotkey, orientation/dual-screen. Then:

```bash
python3 thorctl.py acceptance run --game "Super Smash Bros. Ultimate" \
  --platform switch --app-version 0.2.1 --renderer vulkan \
  --gpu-driver "Balemuni Apex v2 Ultimate SD8Gen2" --gpu-driver-version "Apex-v2" \
  --confirmations controls_ok saves_ok exit_ok --accepted
```

**[DEVICE] Last step:** Cocoon → set as **Home app** (only after Back-navigation
passes). Map systems in Cocoon only for platforms that passed acceptance.

**[AUTO] Final record:**

```bash
python3 thorctl.py frontend commit
python3 thorctl.py report export > thor-setup-report.json
```

---

## Cheat sheet — what lives where

| Thing | Location |
|---|---|
| Staged APKs (hash-pinned) | `apks/` |
| Apex driver (owner-supplied) | `Download/Balemuni_Apex_v2_ULTIMATE_SD8Gen2.zip` on the Thor; intentionally not tracked |
| App/driver hash records | `~/.thor-provision/thorctl-records/` |
| Emulator settings reference | `profiles/ayn-thor-v1.json` |
| Audit trail / reports | `python3 thorctl.py report export` |

## Troubleshooting quick hits

- **`adb: no devices`** → re-accept the debugging prompt; try a different cable
- **Switch black screen or shader exit** → confirm Eden shows *Apex v2 Ultimate SD8 Gen 2* as active, restart Eden, and let the first shader build finish.
- **ROMs/ROMs nesting** → always `adb push sd_card/ROMs /sdcard/` with **no trailing slash**
- **Cocoon empty** → mappings are created only after one successful launch per system
