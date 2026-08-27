#!/usr/bin/env zsh
# Conservative wrapper for the reviewed library intake workflow.
# Ambiguous .iso/.bin/.cue/.chd content is reported until you provide an
# explicit platform decision; no files are copied unless --apply is supplied.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 ingest_library.py "$@" --target "${SD:-sd_card}"
