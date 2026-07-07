<div align="center">

# 🎵 Spotify Downloader Bot

A Telegram bot that downloads Spotify tracks, albums, and playlists as **lossless FLAC** files — with full metadata, cover art, and a complete admin panel.

<p>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white" alt="Python"></a>
  <a href="https://github.com/spotDL/spotify-downloader"><img src="https://img.shields.io/badge/spotDL-4.5-green?logo=spotify&logoColor=white" alt="spotDL"></a>
  <a href="https://github.com/pyrogram/pyrogram"><img src="https://img.shields.io/badge/Pyrogram-2.x-blue?logo=telegram&logoColor=white" alt="Pyrogram"></a>
  <a href="docker-compose.yml"><img src="https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white" alt="Docker"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?longCache=true" alt="License"></a>
  <a href="https://github.com/nikannixro/Spotify-Downloader/stargazers"><img src="https://img.shields.io/github/stars/nikannixro/Spotify-Downloader?style=social" alt="Stars"></a>
  <a href="https://github.com/nikannixro/Spotify-Downloader/commits"><img src="https://img.shields.io/github/last-commit/nikannixro/Spotify-Downloader?logo=github" alt="Last Commit"></a>
</p>

</div>

---

**Spotify Downloader Bot** lets users send any Spotify link directly into Telegram and receive a fully tagged FLAC file — ready to play. It handles single tracks, full albums, and playlists with automatic retries, a persistent file cache, and per-user rate limiting.

The bot uses [spotDL](https://github.com/spotDL/spotify-downloader) as the download engine, which finds the best audio match on YouTube Music, downloads it, and converts it to FLAC via FFmpeg. Metadata is sourced from **Spotify** (primary), [MusicBrainz](https://musicbrainz.org/) (composer, language), and [Deezer](https://www.deezer.com/) (fallback for genre and publisher).

> [!IMPORTANT]
> YouTube Music requires authentication **cookies** to bypass download restrictions — see [Cookies Setup](#-cookies-setup). For personal use only.

## 📑 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Cookies Setup](#-cookies-setup)
- [Bot Usage](#-bot-usage)
- [Admin Panel](#-admin-panel)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [Metadata](#-metadata)
- [Docker](#-docker)
- [Updating](#-updating)
- [Backup & Restore](#-backup--restore)
- [Contributing](#-contributing)
- [Donate](#-donate-)
- [License](#-license)

---

## ✨ Features

### 🎧 For Users

- **Download tracks** — Send any Spotify track link and receive a tagged FLAC file
- **Download albums** — Full album downloads with cover art and track-by-track delivery
- **Download playlists** — All tracks fetched and delivered sequentially
- **Artist profile** — Send a Spotify artist link to see real name, nickname, date of birth (from Wikipedia), and top 10 tracks
- **Inline search** — Search Spotify directly inside any chat using inline mode
  - `artist: <name>` — Search by artist
  - `album: <name>` — Search by album
  - `playlist: <name>` — Search by playlist
  - `track: <name>` — Search by track
  - No prefix — Global search across all types
- **Deep link downloads** — Click a track link from artist profile to download instantly
- **Cancel downloads** — `/cancel` or the inline cancel button stops any in-progress download
- **Rich metadata** — Every file includes title, artist, album, date, genre, track number, composer, publisher, language, and embedded cover art
- **Lossless FLAC** — 32-bit audio, 48 kHz sample rate

### 🛠️ For Admins

- **Stats** — Total users, downloads today, cache size, bot uptime
- **Broadcast** — Send any message to all users with a confirmation step
- **Forced channel join** — Make users join Telegram channels before using the bot
- **Rate limit control** — Adjust per-user download limits and time windows from the panel
- **Maintenance mode** — Lock the bot for all non-admin users with one tap
- **Database backup** — Download the full SQLite database as `database (YYYY-MM-DD).db`
- **Recent downloads** — Check the latest download activity across all users
- **Log channel** — Forward all logs to a dedicated Telegram channel
- **Start message** — Customize the `/start` message shown to users

---

## 🚀 Quick Start

> [!TIP]
> **One-line installer** (Debian/Ubuntu) — clones, installs system deps + Docker, prompts for the required secrets, and starts the container:
>
> ```bash
> bash <(curl -Ls https://raw.githubusercontent.com/nikannixro/Spotify-Downloader/main/install.sh)
> ```

Prefer the manual path? Four steps:

**1. Clone the repository**

```bash
git clone https://github.com/nikannixro/Spotify-Downloader.git
cd Spotify-Downloader
```

**2. Configure the environment**

```bash
cp example.env config.env
# Edit config.env and fill in the 6 required secrets (see Configuration below)
```

**3. Start with Docker Compose**

```bash
docker compose up -d --build
```

**4. Essential Docker commands**

| Action   | Command                                  |
| -------- | ---------------------------------------- |
| Start    | `docker compose up -d`                   |
| Stop     | `docker compose down`                    |
| Restart  | `docker compose restart`                 |
| View logs| `docker compose logs -f`                 |
| Update   | `git pull && docker compose up -d --build` |

> [!NOTE]
> The image is built from source (`Dockerfile`) — there is no registry image to pull. "Update" therefore pulls the latest code and rebuilds.

---

## ⚙️ Configuration

All configuration is done through environment variables in `config.env`.

### Required

| Variable                 | Description                                                                 |
| ------------------------ | --------------------------------------------------------------------------- |
| `TELEGRAM_BOT_TOKEN`     | Bot token from [@BotFather](https://t.me/BotFather)                        |
| `ADMIN_ID`               | Your Telegram numeric user ID                                              |
| `TELEGRAM_API_ID`        | API ID from [my.telegram.org](https://my.telegram.org)                     |
| `TELEGRAM_API_HASH`      | API hash from [my.telegram.org](https://my.telegram.org)                   |
| `SPOTIFY_CLIENT_ID`      | Client ID from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) |
| `SPOTIFY_CLIENT_SECRET`  | Client secret from Spotify Developer Dashboard                             |

### Optional

| Variable                   | Default              | Description                                              |
| -------------------------- | -------------------- | -------------------------------------------------------- |
| `DB_FILE`                  | `data/database.db`   | Path to the SQLite database file                         |
| `COOKIE_FILE`              | `cookies.txt`        | Path to YouTube authentication cookies file              |
| `MAX_CONCURRENT_DOWNLOADS` | `3`                  | Max simultaneous downloads across all users              |
| `DOWNLOAD_TIMEOUT`         | `300`                | Seconds before a download attempt times out              |
| `CACHE_MAX_SIZE_MB`        | `500`                | Max total cache size in megabytes                        |
| `CACHE_MAX_AGE_DAYS`       | `7`                  | Days before cached files are removed                     |
| `RATE_LIMIT_MAX`           | `3`                  | Max downloads per user per window                        |
| `RATE_LIMIT_WINDOW`        | `60`                 | Rate limit window in seconds                             |
| `LOG_LEVEL`                | `INFO`               | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)      |
| `LOG_FILE`                 | `logs/bot.log`       | Path to the log file                                     |

> [!NOTE]
> **Multiple admins** — use `ADMIN_IDS` (comma-separated) instead of `ADMIN_ID`. When set, it takes priority over `ADMIN_ID`.
>
> ```
> ADMIN_IDS=123456789,987654321
> ```

---

## 🍪 Cookies Setup

YouTube Music requires authentication cookies to bypass download restrictions and rate limits.

<details>
<summary><b>Step-by-step cookies export</b></summary>

### 1. Install the browser extension

Install **Get cookies.txt LOCALLY** by kairi:

| Browser | Link |
| --- | --- |
| **Firefox** | [Get cookies.txt LOCALLY — Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/) |
| **Chrome** | [Get cookies.txt LOCALLY — Chrome Web Store](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) |

### 2. Export cookies

1. Log in to [YouTube](https://www.youtube.com) (or [YouTube Music](https://music.youtube.com)) in an incognito tab
2. Navigate to any YouTube page and log in
3. Click the **Get cookies.txt LOCALLY** extension icon in your toolbar
4. Click **Export As** — the extension downloads a `www.youtube.com_cookies.txt` file. Rename it to `cookies.txt`

### 3. Place cookies in the project

```bash
cp ~/Downloads/cookies.txt /path/to/Spotify-Downloader/cookies.txt
```

### 4. Configure the path

In `config.env`:

```
COOKIE_FILE=cookies.txt
```

> [!WARNING]
> Cookies expire over time. If downloads start failing, re-export fresh cookies from your browser.

</details>

---

## 🤖 Bot Usage

### Commands

| Command   | Description                              |
| --------- | ---------------------------------------- |
| `/start`  | Start the bot and show the main menu     |
| `/cancel` | Cancel any in-progress download          |
| `/admin`  | Open the admin panel (admins only)       |

### Downloading

Send any Spotify link to the bot:

```
https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC
https://open.spotify.com/album/6s84SIDdJAm4IVd0FbKWeR
https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
https://open.spotify.com/artist/1dfeR4HaWDbWqFHLkxsg1d
```

**Message flow** when you send a Spotify link:

1. **"⬇️ Downloading..."** — Sent immediately with a cancel button
2. **Cover art photo** — Album/playlist cover with metadata caption
3. **Audio file** — The FLAC file named `ARTIST - TITLE.flac`
4. **"Download has been finished."** — Completion confirmation

For albums and playlists, the cover art and info are sent first, followed by all audio tracks sequentially.

### Artist Profile

Send a Spotify artist link to view:

- **Real name** — From Wikipedia (with fallback to stage name)
- **Nickname** — From Spotify
- **Date of birth** — From Wikipedia (falls back to "Unknown")
- **Top 10 tracks** — Clickable deep links for instant download

### Inline Search

Use the bot in inline mode from any chat:

```
@YourBotUsername artist: ARTIST NAME
@YourBotUsername album: ALBUM NAME
@YourBotUsername playlist: PLAYLIST NAME
@YourBotUsername track: TRACK NAME
@YourBotUsername: Global search
```

> [!NOTE]
> Artist search uses the Spotify API and returns follower counts from Deezer. All searches return Spotify results.

---

## 🛠️ Admin Panel

Access the admin panel with `/admin`. From there:

| Feature          | Description                                                        |
| ---------------- | ------------------------------------------------------------------ |
| Stats            | Total users, downloads today, cache size, uptime                   |
| Recent Downloads | Latest download activity with user and track info                  |
| Broadcast        | Send a message to every user with a confirmation step              |
| Forced Join      | Add/remove mandatory Telegram channels with custom join messages   |
| Rate Limiting    | Increase/decrease download limits and time windows without restart |
| Maintenance Mode | Block all non-admin users while you update the bot                 |
| Log Channel      | Forward all logs to a dedicated Telegram channel                   |
| DB Backup        | Download the database as `database (YYYY-MM-DD).db`                |
| Start Message    | Customize the `/start` message shown to users                      |

---

## 🏗️ Architecture

<details>
<summary><b>High-level architecture & data flow</b></summary>

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
          +----------+-+ +--------+ +--+-----------+
                     |                  |
          +----------v-------+  +------v----------+
          |    inline.py     |  |   callbacks.py  |
          +----------+-------+  +------+----------+
                     |                  |
           +---------v------------------v----------+
           |              plugins/                 |
           |  SpotDLBackend   DownloadCache        |
           |  DeezerClient    DownloadManager      |
           |  ytdl            ytmusic              |
           +------------------+-------------------+
                              |
          +-------------------v-------------------+
          |      External tools & services        |
          |  spotDL  yt-dlp  FFmpeg  Mutagen      |
          |  YouTube Music   Spotify API           |
          |  MusicBrainz API   Deezer API          |
          |  Wikipedia API     SQLite DB           |
          +---------------------------------------+
```

**Data flow for a single track download:**

1. User sends Spotify link → `handle_spotify_link` parses the URL
2. Membership and rate limit are checked
3. spotDL fetches track metadata from Spotify and searches YouTube Music for the best match
4. yt-dlp downloads the audio; FFmpeg converts it to 32-bit FLAC at 48 kHz
5. MusicBrainz queries composer and language using the ISRC
6. If genre or publisher is missing, Deezer is queried as fallback
7. Mutagen embeds all metadata tags and cover art into the FLAC file
8. The file is cached and sent back to the user as `ARTIST - TITLE.flac`

</details>

---

## 📁 Project Structure

<details>
<summary><b>Directory tree</b></summary>

```
Spotify-Downloader/
├── main.py                    # Entry point — Pyrogram client with handler loading
├── config.py                  # Environment variable loading and validation
├── database.py                # SQLite wrapper — users, settings, cache, download log
├── models.py                  # Dataclasses — TrackMetadata, DownloadResult, etc.
├── strings.py                 # User-facing message strings
├── services.py                # Centralized service singletons
├── install.sh                 # Quick Start installer (Debian/Ubuntu)
├── handlers/
│   ├── __init__.py
│   ├── start.py               # /start, /cancel, forced-join verification, deep links
│   ├── download.py            # Spotify link detection, download, artist profile
│   ├── inline.py              # Inline search query handler (Spotify + Deezer)
│   ├── callbacks.py           # All callback query routing
│   ├── states.py              # Per-user conversation state management
│   └── admin/
│       ├── __init__.py
│       ├── panel.py           # Admin panel main menu, stats, backup, start msg
│       ├── broadcast.py       # Broadcast conversation flow
│       ├── channels.py        # Forced-join channel management
│       ├── settings.py        # Rate-limit and general settings
│       └── log_channel.py     # Log channel management
├── plugins/
│   ├── __init__.py
│   ├── spotdl.py              # spotDL backend — download engine, metadata, FFmpeg
│   ├── cache.py               # File cache — hit/miss/eviction logic
│   ├── download_manager.py    # Per-user task tracking and cancellation
│   ├── deezer.py              # Deezer API client for artist search and top tracks
│   ├── ytdl.py                # Standalone yt-dlp download module
│   └── ytmusic.py             # Artist top tracks via Deezer API
├── utils/
│   ├── __init__.py
│   ├── keyboards.py           # All Telegram inline and reply keyboards
│   ├── helpers.py             # URL parsing, filename sanitization, uptime
│   ├── rate_limiter.py        # Sliding-window per-user rate limiter
│   └── log_channel_handler.py # Async logging handler for Telegram log channel
├── cookies.txt                # YouTube authentication cookies (not committed)
├── Dockerfile                 # Docker build
├── docker-compose.yml         # Production compose config
├── requirements.txt           # Python dependencies
└── example.env                # Environment variable template
```

</details>

---

## 🏷️ Metadata

Every downloaded FLAC file contains:

| Field        | Source                              |
| ------------ | ----------------------------------- |
| Artist       | Spotify                             |
| Title        | Spotify                             |
| Track Number | Spotify                             |
| Album        | Spotify                             |
| Release Date | Spotify                             |
| Genre        | Spotify → MusicBrainz → Deezer      |
| Publisher    | Spotify → MusicBrainz → Deezer      |
| Label        | Spotify → MusicBrainz → Deezer      |
| Composer     | MusicBrainz                         |
| Language     | MusicBrainz                         |
| Cover Art    | Spotify (embedded)                  |

The `encoder`, `comment`, `encodedby`, `WOAS`, `ISRC`, and `description` tags are explicitly removed from the final file.

---

## 🐳 Docker

The container is built from the repository `Dockerfile` (no registry image):

- **Base** — Python 3.12 slim with FFmpeg pre-installed
- **Security** — runs as a non-root `botuser`
- **Persistence** — database and cache stored in named volumes (`bot_data`, `bot_cache`)
- **Health** — built-in healthcheck verifies the SQLite database is reachable
- **Restart policy** — `unless-stopped` (auto-recovers after crashes/reboots)
- **Config** — reads `config.env` via compose `env_file`

```bash
docker compose up -d --build      # build & start
docker compose logs -f            # follow logs
docker compose ps                 # status
```

---

## 🔄 Updating

```bash
git pull
docker compose up -d --build
```

> [!TIP]
> Re-export your YouTube cookies periodically — if downloads start failing after an update, expired cookies are usually the cause.

---

## 💾 Backup & Restore

### Backup

Use the admin panel: **`/admin` → DB Backup**. The bot replies with the current database as `database (YYYY-MM-DD).db`.

### Restore

```bash
docker compose down                                # stop the bot
docker cp database.db Spotify-Downloader:/app/data/database.db
docker compose up -d                                # start the bot
```

> [!WARNING]
> Restoring replaces the live database. Always download a fresh backup from the panel before overwriting anything.

---

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome.

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "feat: add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a Pull Request

Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening an issue or pull request.

---

## 💜 Donate

If this project is helpful to you, consider buying me a coffee ☕

**Crypto donations:**

| Currency     | Address |
| ------------ | ------- |
| **BTC**      | `bc1q6r6nnktfftlpqc7l3jfnnmzfgs78703nnjg7al` |
| **ETH**      | `0x52D4e4C13f1A0e99CD2f2Fd98bbA7275E3615Ff7` |
| **USDT (TRC20)** | `TLyaRGRREM2NwsQXkoye7NXziwKzgtgPi2` |

⭐ If you like this project, give it a star — it helps others find it!

---

## 📄 License

Distributed under the **MIT License**. Copyright © 2026 N I K A N.

See [LICENSE](LICENSE) for the full text.
