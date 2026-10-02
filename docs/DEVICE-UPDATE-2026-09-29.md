# AYN Thor device update — 2026-09-29

This note records the completed device-side fixes without copying protected or
owner-supplied binaries into the public repository.

## Verified configuration

- **PS2 / NetherSX2:** BIOS imported; PS2 games live under `ROMs/ps2`.
- **PS3 / aPS3e:** official `PS3UPDAT.PUP` installed through the emulator;
  games live under `ROMs/ps3`.
- **Switch / Eden:** `prod.keys`, `title.keys`, and the extracted Switch
  firmware dump imported through Eden; games live under `ROMs/switch`.
- **Switch GPU driver:** `Balemuni_Apex_v2_ULTIMATE_SD8Gen2.zip` imported in
  Eden's GPU Driver Manager and selected as the active driver. This is the
  Snapdragon 8 Gen 2 / Adreno 740 target used by the Thor's QCS8550 platform.
- **Frontend routing:** Cocoon routes PS2 to NetherSX2, PSP to PPSSPP, PS3 to
  aPS3e, Switch to Eden, and 3DS to Lime3DS.

## Protected-file policy

The repository contains instructions and paths only. It deliberately excludes
BIOS images, PS3/Switch firmware, title/product keys, ROMs, APKs, and custom
GPU-driver archives. Supply those from the user's own device dumps or trusted
official/vendor sources during setup.

## Field notes that prevent common failures

- **No microSD required:** the same layout works on internal storage. Use
  `/storage/emulated/0/ROMs/<platform>/` and keep keys/firmware in their
  emulator-specific folders. Do not create a second `ROMs/ROMs` nesting.
- **ADB recovery:** if `adb devices` reports `ADB server didn't ACK` or an
  interface-plugin error, run `adb kill-server`, `adb start-server`, reconnect
  the cable, unlock the Thor, and accept the USB-debugging RSA prompt.
- **Scoped storage:** Dolphin, Eden, and Cocoon need a one-time Android
  **Use this folder → Allow** grant for each ROM directory. Copying files alone
  does not create that grant.
- **Cocoon duplicates:** a base game, update, and DLC can share one display
  title. A BOTW or Mario Kart “duplicate” is normally a related content file;
  remove only a record whose underlying file is missing or zero bytes.
- **Correct file routing:** PSP uses `.iso`, `.cso`, or `.pbp`; PS2 uses PS2
  ISOs and must launch in NetherSX2. PPSSPP cannot load a PS2 ISO. 3DS files
  route to Lime3DS; Switch `.nsp`/`.xci` files route to Eden.
- **Switch content order:** boot the base title first. Add updates and DLC as
  Eden external content or installed content; do not launch update/DLC packages
  as standalone games.
- **Switch black-screen diagnosis:** if a title builds one shader and returns
  to Eden, inspect the log before replacing keys. On the Thor, the observed
  Vulkan `Format=44` errors pointed to renderer/driver compatibility. The
  Apex v2 Ultimate SD8 Gen 2 driver was imported through Eden's GPU Driver
  Manager, selected, and Eden was restarted.
- **BIOS region:** one compatible, personally dumped PS2 BIOS is normally
  sufficient. USA/EU/Japan BIOS selection is per emulator or title only when a
  game requires a specific region; it is not a per-game copy operation.
- **Thermals and first boot:** custom drivers can take longer to compile shaders
  on first launch. Keep a 60 FPS cap, start at 1x–2x resolution for demanding
  Switch titles, and let shader compilation finish before judging performance.

## Physical controls and touch overlays

The profile now generates controller sections in the offline apply sheets. The
Thor uses an Xbox-style face-button layout: physical bottom/right/left/top map
to the console's Cross-or-A, Circle-or-B, Square-or-X, and Triangle-or-Y
positions as appropriate. Dolphin receives separate GameCube and Wii Classic
profiles; NetherSX2 receives the PS2 Cross/Circle/Square/Triangle profile.

For each emulator, apply the generated default profile after the Thor gamepad
is detected, then set the virtual/on-screen controller to **hidden** or
**opacity 0**. Android emulator settings are app-specific, so the repository
automates the mapping specification and repeatable apply sheet rather than
blindly editing private app databases. Verify one game and save the emulator's
default profile before applying per-game overrides. The generated sheets cover
RetroArch, Azahar, melonDS, Eden, Dolphin, Cemu/CemuDS, DuckStation,
NetherSX2, PPSSPP, and aPS3e; Cocoon and ES-DE are frontends and do not need
console button maps.
