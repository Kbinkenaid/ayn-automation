"""Expand a YouTube URL (video/playlist/channel) into individual video URLs."""
import sys
import yt_dlp

def main(url: str) -> list[str]:
    ydl_opts = {"quiet": True, "extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if "entries" in info:
        ids = []
        for e in info["entries"]:
            if e is None:
                continue
            vid = e.get("id")
            if e.get("ie_key") == "Youtube" and vid:
                ids.append(f"https://www.youtube.com/watch?v={vid}")
            elif e.get("url"):
                ids.append(e["url"])
        return ids
    return [f"https://www.youtube.com/watch?v={info['id']}"]

if __name__ == "__main__":
    for u in main(sys.argv[1]):
        print(u)
