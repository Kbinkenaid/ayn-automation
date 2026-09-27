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

Everything (APKs, Turnip T30 driver) is already staged in `apks/` and
`vendor/drivers/`. Nothing else to prep.

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

## Part 4 — GPU driver: Turnip T30 (5 min, biggest performance win)

**[DEVICE] 1.** Copy `vendor/drivers/turnip_mrpurple_T30-toasted.adpkg.zip`
onto the Thor (or download Mr. Purple Turnip in Chrome — T30 is current).

**[DEVICE] 2.** **Eden**: Settings → GPU Driver Manager → install the T30 zip →
select it as active.

**[DEVICE] 3.** **Cemu/CemuDS** (optional): Settings → Graphics → Custom
Drivers → **+** → pick the T30 zip.

**[AUTO] 4.** Record it in the audit chain:

```bash
python3 thorctl.py driver attest --emulator eden \
  --driver-name "Turnip T30 MrPurple" \
  --driver-version "26.3.0-T30-1.4.359" \
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
| 4 | **Eden** (Switch) | App-picker for *your* keys/firmware (never automate this), ROM folder, docked mode |
| 5 | **CemuDS** (Wii U) | Game folder, keys via app, gamepad screen on bottom, per-game graphics packs |
| 6 | **DuckStation** (PS1) | Your BIOS, 3x, CRT-Lottes shader, run-ahead 1 frame |
| 7 | **NetherSX2** (PS2) | Your BIOS, OpenGL 2.5x, widescreen patches, verify physical controls |
| 8 | **Dolphin** (GC/Wii) | SAF folders, OpenGL 3x, compile shaders before play |
| 9 | **PPSSPP** (PSP) | Data + games folders, 4x |

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
  --gpu-driver "Turnip T30 MrPurple" --gpu-driver-version "26.3.0-T30-1.4.359" \
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
| Turnip T30 driver | `vendor/drivers/turnip_mrpurple_T30-toasted.adpkg.zip` |
| App/driver hash records | `~/.thor-provision/thorctl-records/` |
| Emulator settings reference | `profiles/ayn-thor-v1.json` |
| Audit trail / reports | `python3 thorctl.py report export` |

## Troubleshooting quick hits

- **`adb: no devices`** → re-accept the debugging prompt; try a different cable
- **Low FPS in Switch games** → confirm Eden shows *Turnip T30* as active driver (`driver check --emulator eden`)
- **ROMs/ROMs nesting** → always `adb push sd_card/ROMs /sdcard/` with **no trailing slash**
- **Cocoon empty** → mappings are created only after one successful launch per system
