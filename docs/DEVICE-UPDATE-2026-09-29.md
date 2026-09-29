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
