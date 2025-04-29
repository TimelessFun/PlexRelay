# XTeVe Bridge Service

A Flask-based service that bridges the PPV.wtf API to provide sports streams in M3U and XMLTV formats for XTeVe and other IPTV players.

## Quick Start
**⚠️ Installation Note**
This installation guide was designed for a TrueNAS Scale docker intallation.
The code will work fine on other systems but the installation instructions will be different.

1. Create the directory structure:
```bash
mkdir -p /mnt/<your_pool>/xteve_bridge/app
```

2. Paste the following content:
```yaml
version: "3.9"
services:
  xteve-bridge:
    image: python:3.11-slim
    container_name: xteve_bridge
    ports:
      - "8880:8880"
    volumes:
      - /mnt/<your_pool>/xteve_bridge/app:/app
    working_dir: /app
    environment:
      - PPV_AUTH_TOKEN=your_auth_token_here
    command: >
      sh -c "pip install flask requests &&
             python app.py"
    restart: unless-stopped
```
3. cd To the installation directory
`cd /mnt/<your_pool>/xteve_bridge`

3. Create app.py:
```bash
nano app.py
```

4. Paste the Python code into app.py

5. Click Ctrl + O, Enter, Ctrl + X to save and exit

6. Start the container:
```bash
docker-compose up -d
```

7. Access the following endpoints:
- Status page: http://localhost:8880
- M3U Playlist: http://localhost:8880/playlist.m3u
- XMLTV EPG: http://localhost:8880/epg.xml

8. (Optional) Verify M3U playlist works using `curl http://localhost:8880/playlist.m3u`
You should see something like the following
```m3u
#EXTM3U
#EXTINF:-1 tvg-id="7304" tvg-name="Minnesota Twins vs. Cleveland Guardians" tvg-logo="https://i.imgur.com/DnxoXh3.png" group-title="MLB",Minnesota Twins vs. Cleveland Guardians
https://LINKTOSTREAM
```

## Getting Your Auth Token

1. Go to https://ppv.wtf and log in to your account
2. Open your browser's Developer Tools (F12 or right-click -> Inspect)
3. Go to the Network tab
4. Refresh the page
5. Click the first element that appears
6. Click the "Cookies" section
7. Copy the value of the "ThugSession" value including the quotations - this is your auth token
8. Replace `your_auth_token_here` in the docker-compose.yml with your actual token

## Features

- Fetches and caches sports streams (NBA, NFL, MLB, NHL) from PPV.wtf
- Provides M3U playlist and XMLTV EPG data
- Updates stream data every 6 hours
- Caches MPEG-TS URLs to reduce API calls
- Filters out expired games automatically

## Endpoints

- `/` - Status page showing service information
- `/playlist.m3u` - M3U playlist of available streams
- `/epg.xml` - XMLTV EPG data for the streams

## Docker Commands

- Start the service: `docker-compose up -d`
- View logs: `docker-compose logs -f`
- Stop the service: `docker-compose down`
- Restart the service: `docker-compose restart`

## Notes

- The service caches stream data and MPEG-TS URLs to reduce API calls
- Streams are automatically filtered to show only NBA, NFL, MLB, and NHL games
- Expired games are automatically removed from the playlist
- The service updates every 6 hours to fetch new streams and remove expired ones
- This service is designed for those with VIP status in PPV.wtf