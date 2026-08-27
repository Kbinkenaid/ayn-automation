"""Download audio for one video and transcribe it with MLX Whisper.

Usage: python transcribe.py <youtube-url-or-id>
Idempotent: skips videos whose transcript already exists (use FORCE=1 to redo).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import mlx_whisper
import yt_dlp

ROOT = Path(__file__).parent
TRANSCRIPTS = ROOT / "transcripts"
AUDIO = ROOT / "audio_cache"
MODEL = "mlx-community/whisper-large-v3-turbo"

def slugify(name: str, max_len: int = 80) -> str:
    name = re.sub(r"[^\w\s-]", "", name).strip()
    return re.sub(r"[\s_]+", "-", name)[:max_len].strip("-") or "untitled"

def download_audio(url: str) -> tuple[Path, dict]:
    ydl_opts = {
        "quiet": True,
        "format": "bestaudio/best",
        "outtmpl": str(AUDIO / "%(id)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    path = AUDIO / f"{info['id']}.m4a"
    if not path.exists():
        raise FileNotFoundError(f"audio not found for {url}")
    return path, info

def fmt_ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"

def main(url: str) -> None:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    vid_id = m.group(1) if m else url.strip()

    existing = list(TRANSCRIPTS.glob(f"*[{vid_id}].txt"))
    if existing and not os.environ.get("FORCE"):
        print(f"skip {vid_id} (exists: {existing[0].name})")
        return

    print(f"downloading audio: {vid_id}")
    audio_path, info = download_audio(
        f"https://www.youtube.com/watch?v={vid_id}"
    )
    title = info.get("title", vid_id)

    print(f"transcribing with {MODEL}")
    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=MODEL,
        word_timestamps=False,
        condition_on_previous_text=True,
        initial_prompt=(
            "This is a tech/gaming review video. Keep product names exact: "
            "AYN Thor, Retroid, Steam Deck, ROG Ally, Odin, Android handheld."
        ),
    )

    TRANSCRIPTS.mkdir(exist_ok=True)
    base = TRANSCRIPTS / f"{slugify(title)} [{vid_id}]"
    with open(f"{base}.txt", "w", encoding="utf-8") as f:
        f.write(f"{title}\n{url}\n\n")
        seg = None
        for seg in result["segments"]:
            f.write(f"[{fmt_ts(seg['start'])}] {seg['text'].strip()}\n")
    plain = " ".join(s["text"].strip() for s in result["segments"])
    with open(f"{base}-plain.txt", "w", encoding="utf-8") as f:
        f.write(plain)

    lang = result.get("language", "?")
    dur = result["segments"][-1]["end"] if result["segments"] else 0
    print(f"done: {base}.txt ({lang}, {dur/60:.0f} min)")

if __name__ == "__main__":
    main(sys.argv[1])
