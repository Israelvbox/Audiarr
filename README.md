# Audiarr

Self-hosted Spotify downloader with ID3 tagging and a web UI. Queue up Spotify tracks, playlists, or albums and Audiarr downloads them with proper metadata (title, artist, album, track number, year, cover art).

## Prerequisites

- Python 3.10+
- ffmpeg (installed automatically by the install script)
- Spotify API credentials ([create an app](https://developer.spotify.com/dashboard))

## Quick Start

```bash
git clone https://github.com/israelvara/audiarr
cd audiarr

# 1. Configure your Spotify API credentials
cp .env.example .env
# Edit .env with your Spotify client ID and secret

# 2. Install and run (creates system service)
sudo bash install.sh
```

After installation, visit `http://your-server:8000`, log in, and start adding downloads.

## Manual Setup (Docker / development)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Spotify credentials

# Run
python3 -m app.main
```

## Configuration

| Variable | Required | Description |
|---|---|---|
| `AUDIARR_SPOTIFY_CLIENT_ID` | Yes | Spotify API client ID |
| `AUDIARR_SPOTIFY_CLIENT_SECRET` | Yes | Spotify API client secret |
| `AUDIARR_JWT_SECRET` | No | Auto-generated if empty |
| `AUDIARR_ADMIN_API_KEY` | No | Auto-generated if empty |
| `AUDIARR_DB_PATH` | No | SQLite database path (default: `data/audiarr.db`) |
| `AUDIARR_DOWNLOAD_DIR` | No | Download output directory (default: `music/`) |
| `AUDIARR_LOG_LEVEL` | No | Logging level (default: `INFO`) |

## First Run

On first startup, Audiarr creates an admin user and prints the credentials to the log:

```
NO ADMIN USERS FOUND. AUTO-GENERATED ADMIN:
  Username: admin
  Password: <random>
```

Log in, create another admin user, then delete this auto-generated one.

## Project Structure

```
Audiarr/
├── app/
│   ├── main.py              # FastAPI server & routes
│   ├── config.py            # Configuration (pydantic-settings)
│   ├── auth.py              # Authentication (bcrypt, JWT)
│   ├── queue.py             # Download queue manager
│   ├── database/
│   │   ├── db.py            # SQLite database layer
│   │   ├── models.py        # Data models
│   │   └── schema.sql       # Database schema
│   ├── services/
│   │   ├── downloader.py    # Download engine (yt-dlp)
│   │   ├── spotify.py       # Spotify API client
│   │   ├── tagger.py        # ID3 tag writer (mutagen)
│   │   └── normalizer.py    # Path sanitizer
│   └── static/
│       ├── index.html       # Web UI
│       └── login.html       # Login page
├── install.sh               # System installation script
├── requirements.txt
├── .env.example
└── README.md
```

## Tech Stack

- **Backend:** FastAPI, SQLite (sqlite3)
- **Download:** yt-dlp (via subprocess)
- **Metadata:** Spotify Web API, mutagen (ID3 tags)
- **Auth:** bcrypt, JWT (PyJWT)
- **Frontend:** Vanilla JS, Tailwind CSS (CDN)

## License

MIT
