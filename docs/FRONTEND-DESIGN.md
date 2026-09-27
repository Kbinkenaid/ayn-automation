# AYN Thor — Complete Frontend Design Guide
### Platform-separated homes · per-console logos · per-game box art · fonts & typography

> The goal: the Thor's two screens behave like a curated console. The home is
> split **by platform** — each console gets its own section with its logo —
> and **every game shows its own box art**. Your library is already laid out
> for this: `ROMs/<platform>/Game.file` is the exact structure both frontends
> use to auto-group. This one guide covers BOTH frontends: **Cocoon** (Home)
> and **ES-DE** (library browser).

---

## 1 · Platform separation — "one home per console"

### Cocoon — Smart Folders (automatic)
1. **Start → New → New Folder** → choose **Smart Folder** → type **Platform**.
2. Repeat for every platform you own games for:
   `switch · n3ds · nds · gc · wii · wiiu · psx · ps2 · psp · gba · gbc · snes · nes · n64 · dreamcast · genesis · arcade …`
3. Each Smart Folder **auto-fills** from the matching `ROMs/<platform>/`
   folder — new games appear automatically, no manual sorting ever.
4. Cocoon 3 colors each folder **per platform** (not all blue) and can use
   its **platform icon** as the folder image.
5. Arrange folders on the top-screen grid in your order; the bottom screen
   shows the selected folder's contents.

**Result: the home screen IS the platform list — tap a console, see its games.**

### ES-DE — system view (automatic)
ES-DE's main menu is already platform-separated: every `ROMs/<platform>/`
folder becomes a "system" entry with its logo (from the theme's per-system
art). Nothing to configure — just verify each system shows its correct logo
with the Slate theme installed.

---

## 2 · Per-platform images (console logos)

| Where | How |
|---|---|
| **Cocoon folder icon** | Edit folder → appearance → **Platform icon** (built-in set), or upload a custom PNG/SVG |
| **Cocoon folder hero** | Edit folder → custom artwork → upload console-themed hero image (second screen when selected) |
| **ES-DE system logo** | Automatic from the theme — Slate/Modern/Linear ship per-system SVG logos |
| **ES-DE custom collections** | Drop PNGs into the theme's collection folder (see THEMES-DEV docs) |

**Tip:** the es-de `system-logos` GitLab repo has color + white SVG logos for
every system — **white ones look best** on dark Thor wallpapers.

---

## 3 · Per-game images (box art — the actual game)

### Cocoon
1. Settings → **Scrape** → sources priority: **SteamGridDB first** (best
   quality), then LaunchBox/IGDB/ScreenScraper (LaunchBox + IGDB need no
   credentials).
2. Run a full-library scrape once (online, one-time). Every game gets:
   - **grid icon** (box art / vertical cover)
   - **hero background** (screenshot art on the second screen)
   - **logo** (the game's logotype)
3. Fix matches with the **live-preview picker**: wrong game → edit name →
   refetch; right game, ugly art → **asset picker** (all sources + your own
   uploads).
4. Per-game polish: reposition/resize the logo over the hero so nothing
   overlaps (Cocoon 3 feature).
5. Optional motion: Settings → Personalization → **Hero Settings** →
   animation styles for logos/heroes.

### ES-DE
1. Menu → **SCRAPER** → media source SteamGridDB → **scrape all**.
2. Art appears in the gamelist view (boxes + per-game background).
3. **Cocoon 3 can link to ES-DE's scraped assets** — scrape once, reuse.

### ⭐ Recommended order (avoids double work)
**Scrape in ES-DE first → then in Cocoon enable ES-DE linking →
fill remaining gaps with Cocoon's own scraper.**

---

## 4 · Fonts and typography

### ES-DE (full font control)
- Default font: **Akrobat** (clean, condensed, console-like).
- Any ES-DE theme can ship its own font: place `font.ttf` + `font_bold.ttf`
  in the theme's `core/` folder, then re-select the theme in UI Settings.
- Good pairings: **Akrobat** (safe default), **Saira Condensed**, **Oswald**;
  pixel fonts like **Press Start 2P** for accents only (hard to read at list
  sizes).
- SVG logos can't contain live fonts (LunaSVG limitation) — convert to
  paths; only matters for custom SVGs.

### Cocoon
- Fonts arrive **via themes** (Silk Pod / Theme Studio ZIPs) — themes are
  modular, so keep one theme's font while mixing another's wallpapers/icons.
- **Theme Studio** (web, live dual-screen preview) exports a ready ZIP:
  Settings → Personalization → Theme → **Import ZIP** on the Thor.
- **Glass material** (blur/refraction/tint) complements dark wallpapers and
  white-on-dark typography.

### Recommendation
Start with **ES-DE + Slate (Akrobat)** for the library view and **one Silk
Pod theme whose font you like** for the console home. Swap fonts only after
art is scraped — art matters more than typography, and every font swap
re-renders the grid.

---

## 5 · Full step order (do once, top to bottom)

1. ✅ ROMs already platform-separated on the SSD (`ROMs/<platform>/`)
2. ✅ Frontends staged (Cocoon free · ES-DE paid + free Companion)
3. **Cocoon:** create one Platform Smart Folder per owned platform
4. **ES-DE:** install Slate theme; verify every system logo shows
5. **ES-DE:** scrape box art (SteamGridDB, full library)
6. **Cocoon:** enable ES-DE linking; scrape remaining gaps
7. **Cocoon:** per-game polish — logo position, grid resize
   (Start → Edit Grid → **Y**), ThemePlaza badge widgets
8. Fonts last — ES-DE theme font; Cocoon theme font
9. **Verify BOTH screens:** platform logo on top, box art + hero on bottom
10. Only then → **Set Cocoon as Home**

---

*Everything above is manual on-device by design. The profile's `appearance`
block tracks these as audited manual tasks, and the acceptance gate requires
art rendering on both screens before Home assignment. The scrape pass is the
only online step (one-time); fonts, themes, folders and layout are fully
offline.*
