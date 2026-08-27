# Guide deltas — retrogamecorps.com dual-screen guide (03APR2026)

Source: https://retrogamecorps.com/2025/10/27/dual-screen-android-handheld-guide/

Settings/steps the written guide adds beyond the starter video. Items marked
AUTO are handled by this repo; MANUAL go on the on-device checklist.

## File formats (prepare_sd.py)
- AUTO `--zip-nds` : compress .nds → .zip; melonDualDS + DraStic read zips.
- MANUAL 3DS: use decrypted .3ds/.cci; Azahar also reads .zcci (~25% smaller)
  but Citra MMJ cannot — pick one format if you run both.
- MANUAL Wii U: prefer .wua (game+update+DLC in one compressed file).

## Emulator settings
- Azahar: Debug > V-Sync OFF (input latency). AUTO-candidate for config write.
- Citra MMJ: install "Storage Access Antutu" variant; Screen Layout = Single;
  Internal Res 4x; New 3DS Mode ON.
- DraStic (optional fork): External Display Mode = Correct Aspect Ratio;
  Screen = Bottom; Border = 14% (fork w/ Thor touch: R-YaTian/DraStic_rev_i18n).
- melonDualDS: Renderer OpenGL, 4x, Dual preset internal-top/external-bottom,
  soft input Always Invisible (matches video).
- Cemu: graphics packs download step; quick menu opens via ANDROID BACK BUTTON
  now (left-swipe no longer works) — Show Pad + External Pad Screen toggles.

## Apps
- Optional APKs added to apps.py --optional: Citra MMJ, DraStic-Rev fork,
  PPSSPP-Dual (SapphireRhodonite experimental), Console Launcher beta.
- DS Keyboard (Play Store only — manual), Beacon/iiSU frontends exist but
  Cocoon remains primary.

## Platform notes
- AYN Thor: TOP screen is the Android primary display (AYANEO Pocket DS /
  Retroid attachment are reversed). Emulator "external display" assignments
  must be top-vs-bottom aware per device — our configs assume Thor orientation.
- ROCKNIX Linux is an alternative OS path; out of scope for adb provisioning.
