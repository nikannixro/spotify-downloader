<div align="center">

# Spotify Downloader Bot

A Telegram bot that downloads Spotify tracks, albums, and playlists as **lossless FLAC** files — with full metadata, cover art, and a complete admin panel.

[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![spotDL](https://img.shields.io/badge/spotDL-4.5-green?logo=spotify&logoColor=white)](https://github.com/spotDL/spotify-downloader)
[![Pyrogram](https://img.shields.io/badge/Pyrogram-2.x-blue?logo=telegram)](https://github.com/pyrogram/pyrogram)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)](docker-compose.yml)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Cookies Setup](#cookies-setup)
- [Configuration](#configuration)
- [Bot Usage](#bot-usage)
- [Admin Panel](#admin-panel)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

---

## Overview

Spotify Downloader Bot lets users send any Spotify link directly into Telegram and receive a tagged FLAC file — ready to play. It handles single tracks, full albums, and playlists with automatic retries, a persistent file cache, and per-user rate limiting.

The bot uses [spotDL](https://github.com/spotDL/spotify-downloader) as the download engine, which finds the best audio match on YouTube Music, downloads it, and converts it to FLAC via FFmpeg. Metadata is sourced from Spotify (primary), [MusicBrainz](https://musicbrainz.org/) (composer, language), and [Deezer](https://www.deezer.com/) (fallback for genre and publisher).

---

## Features

### For Users
- **Download tracks** — Send any Spotify track link and receive a tagged FLAC file
- **Download albums** — Full album downloads with cover art and track-by-track delivery
- **Download playlists** — All tracks fetched and delivered sequentially
- **Inline search** — Search Spotify directly inside any chat using inline mode
  - `art: <name>` — Search by artist (Deezer)
  - `alb: <name>` — Search by album
  - `pla: <name>` — Search by playlist
  - `trk: <name>` — Search by track
  - No prefix — Global search across all types
- **Cancel downloads** — `/cancel` or the inline cancel button stops any in-progress download
- **Rich metadata** — Every file includes title, artist, album, date, genre, track number, composer, publisher, language, and embedded cover art
- **Lossless FLAC** — 24-bit audio in a 32-bit container, 8-channel, 48kHz

### For Admins
- **Stats** — Total users, downloads today, cache size, bot uptime
- **Broadcast** — Send any message to all users with a confirmation step
- **Forced channel join** — Make users join Telegram channels before using the bot
- **Rate limit control** — Adjust per-user download limits and time windows from the panel
- **Maintenance mode** — Lock the bot for all non-admin users with one tap
- **Database backup** — Download the full SQLite database file directly in Telegram
- **Recent downloads** — Check the latest download activity across all users
- **Log channel** — Forward WARNING/ERROR logs to a dedicated Telegram channel

---

## Architecture

```
+-----------------------------------------------------------+
|                    Telegram Update                         |
+-----------------------------+-----------------------------+
                              |
                  +-----------v-----------+
                  |    main.py (Pyrogram) |
                  +--+--------+--------+--+
                     |        |        |
          +----------v-+ +---v----+ +--v-----------+
          |   start    | | admin  | |  download    |
          |  handler   | | panel  | |   handler    |
          +----------+-+ +--------+ +--+- ----------+
                     |                  |
          +----------v------------------v----------+
          |              plugins/                  |
          |  SpotDLBackend    DownloadCache        |
          |  DeezerClient     DownloadManager      |
          +-------------------+-------------------+
                              |
          +-------------------v-------------------+
          |      External tools & services        |
          |  spotDL  yt-dlp  FFmpeg  Mutagen      |
          |  YouTube Music   Spotify API           |
          |  MusicBrainz API   Deezer API          |
          |  SQLite DB                             |
          +---------------------------------------+
```

**Data flow for a single track download:**

1. User sends Spotify link → `handle_spotify_link` parses the URL
2. Membership and rate limit are checked
3. spotDL fetches track metadata from Spotify and searches YouTube Music for the best match
4. yt-dlp downloads the audio; FFmpeg converts it to 24-bit FLAC
5. MusicBrainz queries composer and language using the ISRC
6. If genre or publisher is missing, Deezer is queried as fallback
7. Mutagen embeds all metadata tags and cover art into the FLAC file
8. The file is cached and sent back to the user as `ARTIST - TITLE.flac`

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | 3.12 recommended |
| FFmpeg | — | Required for audio conversion to FLAC |
| Telegram Bot Token | — | From [@BotFather](https://t.me/BotFather) |
| Spotify API credentials | — | From [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
| YouTube cookies | — | See [Cookies Setup](#cookies-setup) |

---

## Installation

### VPS Server Setup

**1. Clone the repo**

```bash
git clone https://github.com/nikannixro/Spotify-Downloader.git
cd Spotify-Downloader
```

**2. Install system dependencies**

```bash
# Debian/Ubuntu
apt update && apt install -y ffmpeg

# macOS
brew install ffmpeg
```

**3. Install Python dependencies**

```bash
pip install -r requirements.txt
```

**4. Set up environment variables**

```bash
cp example.env config.env
nano config.env
```

**5. Export YouTube cookies** (see [Cookies Setup](#cookies-setup))

**6. Run the bot**

```bash
python main.py
```

### Docker Setup

**1. Set up environment**

```bash
cp example.env config.env
nano config.env
```

**2. Place `cookies.txt` in the project root**

**3. Build and start**

```bash
docker compose up -d
```

**4. Check logs**

```bash
docker compose logs -f
```

**5. Stop the bot**

```bash
docker compose down
```

The Docker image:
- Uses Python 3.12 slim with FFmpeg pre-installed
- Runs as a non-root `botuser` for security
- Persists database and cache in named Docker volumes
- Includes a healthcheck that verifies the database is reachable

---

## Cookies Setup

YouTube Music requires authentication cookies to bypass download restrictions and rate limits.

### Step 1: Install the browser extension

Install **Get cookies.txt LOCALLY** by kairi:

| Browser | Link |
|---|---|
| **Firefox** | [Get cookies.txt LOCALLY — Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/) |
| **Chrome** | [Get cookies.txt LOCALLY — Chrome Web Store](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) |

### Step 2: Export cookies

1. Log in to [YouTube](https://www.youtube.com) (or [YouTube Music](https://music.youtube.com)) in a incognito tab
2. Navigate to any YouTube page and login
3. Click the **Get cookies.txt LOCALLY** extension icon in your toolbar
4. Click **Export As** — the extension will download a `www.youtube.com_cookies.txt` file change the name to `cookies.txt`

### Step 3: Place cookies in the project

```bash
# Copy the exported cookies.txt to the project root
cp ~/Downloads/cookies.txt /path/to/Spotify-Downloader/cookies.txt
```

### Step 4: Configure the path

In `config.env`, set:

```
COOKIE_FILE=cookies.txt
```

> **Note:** Cookies expire over time. If downloads start failing, re-export fresh cookies from your browser.

---

## Configuration

All configuration is done through environment variables. Copy `example.env` to `config.env` and fill in the values.

### Required

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `ADMIN_ID` | Your Telegram numeric user ID |
| `SPOTIFY_CLIENT_ID` | Client ID from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
| `SPOTIFY_CLIENT_SECRET` | Client secret from Spotify Developer Dashboard |

### Optional

| Variable | Default | Description |
|---|---|---|
| `DB_FILE` | `data/database.db` | Path to the SQLite database file |
| `COOKIE_FILE` | `cookies.txt` | Path to YouTube authentication cookies file |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Max simultaneous downloads across all users |
| `DOWNLOAD_TIMEOUT` | `300` | Seconds before a download attempt times out |
| `CACHE_MAX_SIZE_MB` | `500` | Max total cache size in megabytes |
| `CACHE_MAX_AGE_DAYS` | `7` | Days before cached files are removed |
| `RATE_LIMIT_MAX` | `3` | Max downloads per user per window |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window in seconds |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `LOG_FILE` | `logs/bot.log` | Path to the log file |

---

## Bot Usage

### Commands

| Command | Description |
|---|---|
| `/start` | Start the bot and show the main menu |
| `/cancel` | Cancel any in-progress download |

### Downloading

Send any Spotify link to the bot:

```
https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC
https://open.spotify.com/album/6s84SIDdJAm4IVd0FbKWeR
https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
```

### Message Flow

When you send a Spotify link, the bot responds in this order:

1. **"⬇️ Downloading..."** — Sent immediately with a cancel button
2. **Cover art photo** — Album/playlist cover with metadata caption
3. **Audio file** — The FLAC file named `ARTIST - TITLE.flac`
4. **"Download has been finished."** — Completion confirmation

For albums and playlists, the cover art and info are sent first, followed by all audio tracks sequentially.

### Inline Search

Use the bot in inline mode from any chat:

```
@YourBotUsername art: ARTIST NAME
@YourBotUsername alb: ALBUM NAME
@YourBotUsername pla: PLAYLIST NAME
@YourBotUsername trk: TRACK NAME
@YourBotUsername: Global search
```

> **Note:** Artist search (`art:`) uses the Deezer API and returns Deezer artist links. All other searches use the Spotify API.

---

## Admin Panel

Access the admin panel with `/admin`. From there:

| Feature | Description |
|---|---|
| Stats | Total users, downloads today, cache size, uptime |
| Recent Downloads | Latest download activity with user and track info |
| Broadcast | Send a message to every user with a confirmation step |
| Forced Join | Add/remove mandatory Telegram channels with custom join messages |
| Rate Limiting | Increase/decrease download limits and time windows without restart |
| Maintenance Mode | Block all non-admin users while you update the bot |
| Log Channel | Forward WARNING/ERROR logs to a dedicated Telegram channel |
| DB Backup | Download the full SQLite database as a file |
| Start Message | Customize the `/start` message shown to users |

---

## Project Structure

```
Spotify-Downloader/
|
+-- main.py                    # Entry point — Pyrogram client with handler loading
+-- config.py                  # Environment variable loading and validation
+-- database.py                # SQLite wrapper — users, settings, cache, download log
+-- models.py                  # Dataclasses — TrackMetadata, DownloadResult, etc.
+-- strings.py                 # User-facing message strings
+-- services.py                # Centralized service singletons
|
+-- handlers/
|   +-- admin_states.py        # Per-user conversation state management
|   +-- start_handler.py       # /start, /cancel, forced-join verification
|   +-- download_handler.py    # Spotify link detection and download orchestration
|   +-- inline_handler.py      # Inline search query handler (Spotify + Deezer)
|   +-- callback_handler.py    # All callback query routing
|   +-- admin/
|       +-- panel_handler.py   # Admin panel main menu, stats, backup
|       +-- broadcast_handler.py  # Broadcast conversation flow
|       +-- channel_handler.py    # Forced-join channel management
|       +-- settings_handler.py   # Rate-limit and general settings
|       +-- log_channel_handler.py  # Log channel management
|
+-- plugins/
|   +-- spotdl.py              # spotDL backend — download engine, metadata, FFmpeg
|   +-- download_cache.py      # File cache — hit/miss/eviction logic
|   +-- download_manager.py    # Per-user task tracking and cancellation
|   +-- deezer_client.py       # Deezer API client for artist search
|
+-- utils/
|   +-- telegram_keyboards.py  # All Telegram inline and reply keyboards
|   +-- formatting.py          # URL parsing, filename sanitization, uptime
|   +-- rate_limiter.py        # Sliding-window per-user rate limiter
|   +-- log_channel_handler.py # Async logging handler for Telegram log channel
|
+-- cookies.txt                # YouTube authentication cookies (not committed)
+-- Dockerfile                 # Docker build
+-- docker-compose.yml         # Production compose config
+-- requirements.txt           # Python dependencies
+-- example.env                # Environment variable template
```

---

## Metadata

Every downloaded FLAC file contains:

| Field | Source |
|---|---|
| Artist | Spotify |
| Title | Spotify |
| Track Number | Spotify |
| Album | Spotify |
| Release Date | Spotify |
| Genre | Spotify → MusicBrainz → Deezer |
| Publisher | Spotify → MusicBrainz → Deezer |
| Composer | MusicBrainz |
| Language | MusicBrainz |
| Cover Art | Spotify (embedded) |
| ISRC | — (not embedded) |

The `encoder`, `comment`, `encodedby`, `WOAS`, and `ISRC` tags are explicitly removed from the final file.

---

## Contributing

Contributions, bug reports, and feature requests are welcome.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

### Dev Setup

```bash
git clone https://github.com/nikannixro/Spotify-Downloader.git
cd Spotify-Downloader
pip install -r requirements.txt
cp example.env config.env
# fill in config.env with test credentials
python main.py
```

---
