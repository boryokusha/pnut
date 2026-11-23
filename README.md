```text
  █▀█ █▄░█ █░█ ▀█▀
  █▀▀ █░▀█ █▄█ ░█░
```

# pnut — Minimalist Audiophile Terminal Music Player

A lightweight, keyboard-driven terminal music player built for **CachyOS**, **Arch Linux**, and **PipeWire**. Designed for audiophiles and terminal ricing enthusiasts.

Features **Bit-Perfect Lossless Playback**, **Embedded Parametric AutoEQ for IEMs**, **Live CAVA Spectrum Visualizer**, **Synced Lyrics (Karaoke)**, **Playback Queue**, **Favorites**, **Shuffle & Repeat**, and **Sleep Timer**.

---

## ✨ Features

* **Integrated Compact Header:**
  * Top-Left: Minimalist 2-line Unicode block `PNUT` logo.
  * Top-Right: Track title, artist, Hi-Res format badges, flow indicators (`[🔀]`, `[🔁]`, `[★]`, `[🌙]`), volume, and timelapse progress bar.
* **Studio Split View (`v` key):**
  * **Left Panel:** Large album cover art (Chafa / ASCII Art).
  * **Right Panel:** Live vertical **CAVA Spectrum Visualizer** with frequency band analysis (Bass, Mid, Treble).
  * **Synced Lyrics Mode (`l` key):** In Studio view, press `l` to toggle between Spectrum and real-time auto-scrolling lyrics (powered by [LRCLIB](https://lrclib.net/)).
* **Playback Flow Conveniences:**
  * **Queue (`a` key):** Add any track to queue without interrupting current song. Dedicated `[5] Queue` tab.
  * **Favorites (`f` key):** Mark tracks with `★` and manage them in `[4] Favs` tab (saved permanently in `~/.config/pnut/favorites.json`).
  * **Shuffle & Repeat (`z` / `r` keys):** Toggle shuffle (`🔀`) and cycle repeat modes (`🔁 All`, `🔂 Single`, `Off`).
  * **Seamless Auto-Transition:** Automatically transitions to next track, queue, or loop on track end.
  * **Sleep Timer (`s` -> Sleep Timer):** Set timer (15, 30, 45, 60, 90 mins) to automatically pause playback.
* **Parametric AutoEQ for IEM Earphones:**
  * Pre-configured AutoEQ profiles: **Tangzu Wan'er S.G**, **Moondrop Chu II**, **7Hz Salnotes Zero**, plus Bass Boost, V-Shape, and Flat Bypass.
  * Easy custom profile import via `~/.config/pnut/eq/` or CLI (`python import_autoeq.py`).
* **Ricing-Ready Theme Engine (`s` -> Themes):**
  * Pre-loaded with ricing favorites: **Catppuccin Mocha**, **Gruvbox Dark**, **Nord**, **Dracula**, **Tokyo Night**, **Rosé Pine**, and **Default**.
  * Preserves native terminal background (`-1`) for transparency and compositor blur.
* **Extensive Audio Format Support:**
  * Lossless & Hi-Res: `.flac`, `.wav`, `.dsf`, `.dff`, `.aiff`, `.alac`, `.ape`, `.wv`, `.mka`
  * Compressed & Standard: `.opus`, `.ogg`, `.mp3`, `.m4a`, `.aac`, `.wma`

---

## 🚀 Quick Start

### 1. Automated Installation

Run the automated installer to set up all system dependencies (`cava`, `mpv`, `chafa`, `ffmpeg`):

```bash
cd ~/Documents/flac_player
./install.sh
```

### 2. Launch pnut

```bash
./pnut
```

*(Or specify a music folder directly: `./pnut ~/Music`)*

---

## ⌨️ Keyboard Shortcuts

| Key | Category | Action |
| :--- | :--- | :--- |
| **`z`** | **Playback Flow** | **Toggle Shuffle (`🔀`)** |
| **`r`** | **Playback Flow** | **Cycle Repeat: `Off` → `All (🔁)` → `Single (🔂)`** |
| **`a`** | **Playback Flow** | **Add selected track to Queue** |
| **`f`** | **Playback Flow** | **Toggle Favorite (`★`)** |
| **`d`** | **Playback Flow** | **Remove item from Queue (in `[5] Queue` tab)** |
| **`1` – `5`** | **Navigation** | **Tabs: `1-Tracks` \| `2-Artists` \| `3-Albums` \| `4-Favs` \| `5-Queue`** |
| **`o`** | **Library** | **Open Music Directory Selector (`./music`, `~/Music`, custom)** |
| **`v`** | **View** | **Toggle View: Studio (Cover & Visualizer) ↔ Library** |
| **`l`** | **Studio** | **Toggle Spectrum Visualizer ↔ Synced Lyrics** |
| **`s`** | **Settings** | **⚙ Open Settings (Themes, IEM EQ, Sleep Timer, Shortcuts)** |
| **`Enter`** | **Control** | **Play track / Filter by selected item** |
| **`c`** | **Filter** | **Clear active filter (Return to full library)** |
| **`Space`** | **Playback** | **Play / Pause** |
| **`h` / `Right`** | **Playback** | **Seek -5s / +5s** |
| **`n` / `b`** | **Playback** | **Next / Previous track** |
| **`+` / `-`** | **Volume** | **Volume up / down** |
| **`/`** | **Search** | **Search library (`a:artist`, `al:album`, `t:title`, or general)** |
| **`q`** | **General** | **Quit pnut** |

---

## 🎧 Custom IEM EQ Profiles

1. Drop your Equalizer APO `.txt` or `.json` file into `~/.config/pnut/eq/`.
2. Or use the import utility:
   ```bash
   python import_autoeq.py profile.txt "Earphone Model Name"
   ```
3. Open **`s`** (Settings) -> **IEM EQ Profiles** and press **Enter** to activate.

---

## 📜 Credits & Acknowledgements

* **[CAVA](https://github.com/karlstav/cava):** Console-based Audio Visualizer by Karl Stavestrand (MIT License).
* **[LRCLIB](https://lrclib.net/):** Free and open-source synced lyrics provider.
* **[AutoEq](https://github.com/jaakkopasanen/AutoEq):** IEM headphone equalization target curves and Crinacle measurements by Jaakko Pasanen.
* **[MPV](https://mpv.io/) & [FFmpeg](https://ffmpeg.org/):** Core audio engine and filter processing.
* **[Chafa](https://hpjansson.org/chafa/):** Terminal image character rendering engine.
