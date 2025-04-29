# PlexRelay

A complete IPTV solution that combines a Python bridge service with xTeVe to provide sports streams in M3U and XMLTV formats for Plex and other IPTV players.

## Table of Contents
- [Quick Start](#quick-start)
- [Getting Your Auth Token](#getting-your-auth-token)
- [Features](#features)
- [Components](#components)
- [Endpoints](#endpoints)
- [Docker Commands](#docker-commands)
- [Notes](#notes)

## Quick Start
**⚠️ Installation Note**
- This installation guide was designed for a TrueNAS Scale docker installation. YMMV with installation on other platforms
- This service was designed to use PPV.wtf as the source for streams. Configuration is neeeded for other providers

1. Create the directory structure:
```bash
mkdir -p /mnt/<your_pool>/plexrelay
mkdir -p /mnt/<your_pool>/xteve
```

2. Paste the following content:
```yaml
version: "3.9"

services:
  plexrelay:
    image: python:3.11-slim
    container_name: plexrelay-bridge
    ports:
      - "8880:8880"
    volumes:
      - /mnt/<your_pool>/plexrelay:/app
    working_dir: /app
    environment:
      - PPV_AUTH_TOKEN=your_auth_token_here
    command: >
      sh -c "pip install flask requests &&
             python app.py"
    restart: unless-stopped

  xteve:
    image: linuxserver/xteve:latest
    container_name: xteve
    environment:
      - PUID=568  # change to match your user ID
      - PGID=568  # change to match your group ID
      - TZ=America/Vancouver  # change to your timezone
    volumes:
      - /mnt/<your_pool>/xteve:/config
    ports:
      - "34400:34400"  # xTeVe web interface
    restart: unless-stopped
    depends_on:
      - plexrelay
```

4. Navigate to the installation directory using shell
`cd /mnt/<your_pool>/plexrelay`

5. Create app.py:
```bash
nano app.py
```

6. Paste the Python code into app.py

7. Click Ctrl + O, Enter, Ctrl + X to save and exit

8. Start the containers:
```bash
docker-compose up -d
```

9. Access the services:
- Bridge Status: http://localhost:8880
- xTeVe Interface: http://localhost:34400/web

10. (Optional) Verify M3U playlist works using `curl http://localhost:8880/playlist.m3u`
You should see something like the following:
```m3u
#EXTM3U
#EXTINF:-1 tvg-id="7304" tvg-name="Minnesota Twins vs. Cleveland Guardians" tvg-logo="https://i.imgur.com/DnxoXh3.png" group-title="MLB",Minnesota Twins vs. Cleveland Guardians
https://LINKTOSTREAM
```

11. Configure xTeVe:
   - Go to http://localhost:34400/web
   - Navigate to Settings → M3U/XSPF
   - Add M3U Playlist:
     * Name: "PlexRelay"
     * URL: http://plexrelay:8880/playlist.m3u
     * EPG URL: http://plexrelay:8880/epg.xml
   - Click Test, then Save
   - Go to Mappings to configure your channels
   - Save your configuration

## Getting Your Auth Token

1. Go to [PPV.wtf](https://ppv.wtf) and log in to your account
2. Open your browser's Developer Tools (F12 or right-click -> Inspect)
3. Go to the Network tab
4. Refresh the page
5. Click the first element that appears
6. Click the "Cookies" section
7. Copy the value of the "ThugSession" value including the quotations - this is your auth token
8. Replace `your_auth_token_here` in the [docker-compose.yml](#quick-start) with your actual token

## Features

- Fetches and caches sports streams (NBA, NFL, MLB, NHL) from [PPV.wtf](https://ppv.wtf)
- Provides M3U playlist and XMLTV EPG data
- Updates stream data every 6 hours
- Caches MPEG-TS URLs to reduce API calls
- Filters out expired games automatically
- Integrates with xTeVe for channel management and EPG

## Components

### PlexRelay Bridge
- Python-based service that interfaces with [PPV.wtf](https://ppv.wtf)
- Provides M3U and XMLTV endpoints
- Accessible at port 8880

### xTeVe
- Channel management and EPG integration
- Provides a unified M3U playlist for Plex
- Web interface for configuration
- Accessible at port 34400

## Endpoints

### Bridge Service
- `/` - Status page showing service information
- `/playlist.m3u` - M3U playlist of available streams
- `/epg.xml` - XMLTV EPG data for the streams

### xTeVe
- `/web` - Web interface for configuration
- `/playlist.m3u` - Final M3U playlist for Plex
- `/epg.xml` - Final EPG data for Plex

## Docker Commands

- Start all services: `docker-compose up -d`
- View logs: `docker-compose logs -f`
- Stop all services: `docker-compose down`
- Restart all services: `docker-compose restart`
- View logs for specific service: `docker-compose logs -f plexrelay` or `docker-compose logs -f xteve`

## Notes

- The bridge service caches stream data and MPEG-TS URLs to reduce API calls
- Streams are automatically filtered to show only NBA, NFL, MLB, and NHL games
- Expired games are automatically removed from the playlist
- The service updates every 6 hours to fetch new streams and remove expired ones
- This service is designed for those with VIP status in [PPV.wtf](https://ppv.wtf)
- xTeVe provides the final M3U playlist that should be used in Plex
