#!/usr/bin/env zsh
# ============================================================
#  AYN THOR — ONE-SHOT FULL SETUP
#  Downloads all emulators, builds the SD layout, fetches the
#  homebrew game preset, generates configs, and deploys to any
#  connected Android device (real Thor or emulator).
#
#    ./setup_all.sh                 # full run (device required for deploy)
#    ./setup_all.sh --no-deploy     # prepare everything Mac-side only
#    ./setup_all.sh --auto-games 5  # +5 random homebrew per platform
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

NO_DEPLOY=0; EXTRA=()
for arg in "$@"; do
  case $arg in
    --no-deploy) NO_DEPLOY=1 ;;
    *) EXTRA+=("$arg") ;;
  esac
done

echo "── [1/6] emulator apps ──────────────────────────"
python3 apps.py

echo "── [2/6] SD card structure + BIOS checklist ─────"
python3 prepare_sd.py

echo "── [3/6] homebrew game preset ───────────────────"
python3 get_games.py ${EXTRA:+sd_card "${EXTRA[@]}"} || python3 get_games.py

echo "── [4/6] RetroArch config (guide settings) ──────"
python3 make_retroarch_cfg.py

echo "── [5/6] Obtainium pack (on-device updates) ─────"
cp -f vendor/emulation-pack-dual-screen.json sd_card/Download_obtainium-pack.json \
  && mkdir -p sd_card/ROMs/_extras \
  && cp -f vendor/emulation-pack-dual-screen.json sd_card/ROMs/_extras/obtainium-emulation-pack-dual-screen.json

if [[ $NO_DEPLOY == 1 ]]; then
  echo "── [6/6] deploy skipped (--no-deploy) ───────────"
else
  echo "── [6/6] deploying to device ────────────────────"
  ./deploy.sh
fi

echo ""
echo "Done. Contents:"
echo "  apks/       → $(ls apks/*.apk 2>/dev/null | wc -l | tr -d ' ') emulators"
echo "  sd_card/    → SD image (copy to card or let deploy.sh push)"
echo "  add_games.sh <folder> [--push] → grow your library anytime"
