# ReClip

A self-hosted, open-source video and audio downloader with a clean web UI. Paste links from YouTube, TikTok, Instagram, Twitter/X, and 1000+ other sites — download as MP4 or MP3.

![Python](https://img.shields.io/badge/python-3.8+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Desktop App](https://img.shields.io/badge/desktop-pyinstaller-purple)

![ReClip](assets/preview-mp3.png)

## Desktop App

A standalone desktop app is bundled as a single `ReClip.exe` (Windows). No browser needed — double-click `ReClip.bat` to launch. The exe includes yt-dlp and ffmpeg built in.

## Features

- Download videos from 1000+ supported sites (via [yt-dlp](https://github.com/yt-dlp/yt-dlp))
- MP4 video or MP3 audio extraction
- Quality/resolution picker
- Bulk downloads — paste multiple URLs at once
- Automatic URL deduplication
- Clean, responsive UI — no frameworks, no build step
- Single Python file backend (~150 lines)
- Animated splash screen with ReClip branding
- Download progress bar with speed and ETA
- Save file dialog — choose where to save after download
- Watch/preview downloaded files before saving
- Download history with re-download and clear options
- Settings panel (save location, history toggle)
- Right-click paste on URL input
- **Batch import from file** — load URLs from a .txt file
- **Auto-subtitle download** — fetch SRT/VTT subtitles alongside video
- **Trim/clip download** — download only a time range (e.g. 0:30–2:00)
- **Format presets** — save preferred quality/format combos
- **Duplicate detection** — warn if URL already in history
- **Dark/light theme toggle** — switch between warm beige and dark mode
- **Browser extension** — one-click send URL to ReClip from any page

## Quick Start

### Desktop App (Windows)

```bash
git clone https://github.com/bugsfreeWeb/Reclip.git
cd Reclip
./ReClip.bat
```

The first run will build `dist\ReClip.exe` automatically.

### Web App

```bash
brew install yt-dlp ffmpeg    # or apt install ffmpeg && pip install yt-dlp
git clone https://github.com/bugsfreeWeb/Reclip.git
cd Reclip
./reclip.sh
```

Open **http://localhost:8899**.

Or with Docker:

```bash
docker build -t reclip . && docker run -p 8899:8899 reclip
```

## Usage

1. Paste one or more video URLs into the input box (or import from a .txt file)
2. Choose **MP4** (video) or **MP3** (audio)
3. Optionally enable **Subtitles** and/or **Trim** (set start/end time in seconds)
4. Click **Fetch** to load video info and thumbnails
5. Select quality/resolution if available
6. Click **Download** on individual videos, or **Download All**
7. After download, click **Save** to choose where to save the file
8. Click **Watch** to preview the downloaded file

## Browser Extension

1. Open `chrome://extensions` in Chrome/Edge
2. Enable "Developer mode"
3. Click "Load unpacked" and select the `extension/` folder
4. Right-click any video page → "Send to ReClip"
5. Or click the extension icon to send the current tab URL

## Supported Sites

Anything [yt-dlp supports](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md), including:

YouTube, TikTok, Instagram, Twitter/X, Reddit, Facebook, Vimeo, Twitch, Dailymotion, SoundCloud, Loom, Streamable, Pinterest, Tumblr, Threads, LinkedIn, and many more.

## Stack

- **Backend:** Python + Flask (~150 lines)
- **Frontend:** Vanilla HTML/CSS/JS (single file, no build step)
- **Desktop:** PyInstaller + pywebview (single-file exe)
- **Download engine:** [yt-dlp](https://github.com/yt-dlp/yt-dlp) + [ffmpeg](https://ffmpeg.org/)
- **Dependencies:** Flask, yt-dlp, imageio-ffmpeg, pywebview

## Building the Desktop App

```bash
pip install flask yt-dlp imageio-ffmpeg pywebview pyinstaller
python -m PyInstaller --onefile --windowed --name "ReClip" \
    --add-data "templates;templates" \
    --add-data "static;static" \
    --add-data "tools;tools" \
    --add-data "app.py;." \
    --add-data "desktop.py;." \
    --hidden-import yt_dlp \
    --hidden-import imageio_ffmpeg \
    --hidden-import webview \
    desktop.py
```

Output: `dist\ReClip.exe`

## Credits

Project: ReClip (Custom) — Organized by **Bugsfree Studio**

Based on [averygan/reclip](https://github.com/averygan/reclip)

## Disclaimer

This tool is intended for personal use only. Please respect copyright laws and the terms of service of the platforms you download from. The developers are not responsible for any misuse of this tool.

## License

[MIT](LICENSE)
