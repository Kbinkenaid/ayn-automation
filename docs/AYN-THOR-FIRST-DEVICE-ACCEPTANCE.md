# AYN Thor first-device acceptance

`profiles/ayn-thor-v1.json` is an auditable recommendation profile derived from
the local starter-guide transcript. It is deliberately not an Android UI macro:
emulator package IDs, settings schemas, SAF grants, GPU drivers, and app-private
storage differ across versions and need a connected-device check. Its plan is
non-authorizing, including when capability JSON is forged.

Before connection, validate the profile and produce a non-authorizing plan:

```zsh
python3 emulator_profiles.py validate
python3 emulator_profiles.py plan --serial YOUR_SERIAL --rom-root /SAF-selected-or-device-discovered/ROMs
```

On first connection, enable USB debugging, identify the single intended serial,
and run `python3 probe.py SERIAL --refresh`. A future deployment command must
require that exact serial (never choose the first `adb devices` result), confirm
free space and shared-storage access, discover package/version/signature data,
and fail hard on any APK install failure. It must hash every ROM push and write
a JSON report. Do not write Android/data or app configuration unless the probe
confirms it is safely writable. Reports and logs must contain only metadata and
hashes: never emit BIOS content, firmware, title keys, API keys, passwords, or
other credentials.

Acceptance sequence:

1. Copy the already-reviewed ROM staging tree; compare SHA-256 results.
2. For each app, grant its folder access in the system picker, choose the listed
   ROM folder, and use your own BIOS, firmware, title keys, and credentials.
3. Launch one owned title per platform; test controls, touch/stylus where
   applicable, saves, exit hotkeys, and orientation/dual-screen layout.
4. Record the emulator version, renderer, and (for Eden) exact GPU-driver build
   that passes the launch test. Updates/DLC are verified manually by title ID.
5. In Cocoon, enable Smart Folders, create mappings only for validated systems,
   rescan, and test a frontend launch before setting Cocoon as the Home app.

The profile contains guide defaults (RetroArch Vulkan/core/hotkey guidance,
Azahar and melonDS dual-screen preferences, and per-system paths) as starting
points, not universal compatibility claims. Reduce resolution or change renderer
on a per-game basis.
