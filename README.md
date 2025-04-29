# PlexRelay

A complete IPTV solution that combines a Python bridge service with xTeVe to provide sports streams in M3U and XMLTV formats for Plex and other IPTV players.

## Prerequisites

Before you begin, ensure you have:

1. **Plex Pass Subscription**
   - Required for Live TV & DVR functionality
   - Available at [plex.tv/plans](https://www.plex.tv/plans)

2. **PPV.wtf VIP Account**
   - Required for accessing the sports streams
   - Available at [ppv.wtf](https://ppv.wtf)
   - Alt links @ [ppv.zone](https://ppv.zone)

3. **Docker and Docker Compose**
   - Required for running the services
   - Installation instructions available at [docs.docker.com](https://docs.docker.com/get-docker/)

## Table of Contents
- [Quick Start](#quick-start)
- [Getting Your Auth Token](#getting-your-auth-token)
- [Connecting to Plex](#connecting-to-plex)
- [Features](#features)
- [Components](#components)
- [Endpoints](#endpoints)
- [Docker Commands](#docker-commands)
- [Notes](#notes)

## Quick Start

1. Create the directory structure:
```bash
mkdir -p /mnt/<yourpool>/plexrelay
mkdir -p /mnt/<yourpool>/xteve
```

2. Create a docker-compose.yml file and paste the following content:
```yaml
version: "3.9"

services:
  plexrelay:
    image: ghcr.io/timelessfun/plexrelay:latest
    container_name: plexrelay-bridge
    ports:
      - "8880:8880"
    volumes:
      - /mnt/<yourpool>/plexrelay:/app/data
    environment:
      - PPV_AUTH_TOKEN=your_auth_token_here
    restart: unless-stopped

  xteve:
    image: alturismo/xteve:latest
    container_name: xteve
    environment:
      - PUID=568  # change to match your user ID
      - PGID=568  # change to match your group ID
      - TZ=America/Vancouver  # change to your timezone
    volumes:
      - ./xteve:/config
    ports:
      - "34400:34400"  # xTeVe web interface
    restart: unless-stopped
    depends_on:
      - plexrelay
```

3. Replace the following in the docker-compose.yml:
   - `your_auth_token_here` with your PPV.wtf auth token ([see below for instructions](#getting-your-auth-token))
   - `<yourpool>` with your actual storage pool name

4. Start the services:
```bash
docker-compose up -d
```

5. Access the services:
- Bridge Status: http://localhost:8880
- xTeVe Interface: http://localhost:34400/web

6. (Optional) Verify M3U playlist works using 
```bash
curl http://localhost:8880/playlist.m3u
```

You should see something like the following:
```m3u
#EXTM3U
#EXTINF:-1 tvg-id="7304" tvg-name="Minnesota Twins vs. Cleveland Guardians" tvg-logo="https://i.imgur.com/DnxoXh3.png" group-title="MLB",Minnesota Twins vs. Cleveland Guardians
https://LINKTOSTREAM
```

7. Configure xTeVe:
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
8. Replace `your_auth_token_here` in the docker-compose.yml with your actual token

## Connecting to Plex

1. In xTeVe (http://localhost:34400/web):
   - Go to Settings → M3U/XSPF
   - Note the "M3U URL" and "XMLTV URL" values
   - These will be something like:
     * M3U: `http://localhost:34400/playlist.m3u`
     * XMLTV: `http://localhost:34400/epg.xml`

2. In Plex:
   - Go to Settings → Live TV & DVR
   - Click "Set Up Plex DVR"
   - Choose "M3U Playlist" as the source
   - Enter the M3U URL from xTeVe
   - Enter the XMLTV URL from xTeVe
   - Click "Next"
   - Select the channels you want to include
   - Click "Next"
   - Choose your DVR settings (recording quality, etc.)
   - Click "Next"
   - Review your settings and click "Finish"

3. Accessing Live TV:
   - In Plex, go to the "Live TV" section
   - Your configured channels should now be available
   - You can watch live streams and schedule recordings

4. Troubleshooting:
   - If channels don't appear, verify the M3U and XMLTV URLs are accessible
   - Check xTeVe logs for any stream issues
   - Ensure your Plex server can reach the xTeVe container
   - Try refreshing the guide data in Plex if EPG is not showing

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

- This installation guide was designed for a TrueNAS Scale docker installation. 
- The bridge service caches stream data and MPEG-TS URLs to reduce API calls
- Streams are automatically filtered to show only NBA, NFL, MLB, and NHL games
- Expired games are automatically removed from the playlist
- The service updates every 6 hours to fetch new streams and remove expired ones
- This service is designed for those with VIP status in [PPV.wtf](https://ppv.wtf)
- xTeVe provides the final M3U playlist that should be used in Plex

## Storage and Caching

The PlexRelay service stores its cache data in the `/mnt/<yourpool>/plexrelay` directory. This includes:
- Stream information cache
- MPEG-TS URL cache
- All cached data is automatically refreshed every 6 hours

This persistent storage ensures that:
- The service starts up quickly using cached data
- Stream information is preserved across container restarts
- API calls are minimized by using cached data
