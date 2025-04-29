# XTeVe Bridge Service

A Flask-based service that bridges the PPV.wtf API to provide sports streams in M3U and XMLTV formats for XTeVe and other IPTV players.

## Features

- Fetches and caches sports streams (NBA, NFL, MLB, NHL) from PPV.wtf
- Provides M3U playlist and XMLTV EPG data
- Updates stream data every 6 hours
- Caches MPEG-TS URLs to reduce API calls
- Filters out expired games automatically

## Requirements

- Python 3.x
- Flask
- APScheduler
- Requests

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd xteve
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install flask apscheduler requests
```

## Configuration

Edit `app.py` to set your configuration:

```python
# Auth Token for API access
AUTH_TOKEN = "your_auth_token_here"

# How often to refresh data (in seconds)
REFRESH_INTERVAL_SECONDS = 21600  # 6 hours

# Port for the Flask service
FLASK_PORT = 8880
```

## Usage

1. Start the service:
```bash
python app.py
```

2. Access the following endpoints:
- Status page: http://localhost:8880
- M3U Playlist: http://localhost:8880/playlist.m3u
- XMLTV EPG: http://localhost:8880/epg.xml

3. Use the M3U playlist URL in your IPTV player (XTeVe, Plex, etc.)

## Endpoints

- `/` - Status page showing service information
- `/playlist.m3u` - M3U playlist of available streams
- `/epg.xml` - XMLTV EPG data for the streams

## Notes

- The service caches stream data and MPEG-TS URLs to reduce API calls
- Streams are automatically filtered to show only NBA, NFL, MLB, and NHL games
- Expired games are automatically removed from the playlist
- The service updates every 6 hours to fetch new streams and remove expired ones
