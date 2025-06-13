import os
import json
import requests
import time
import logging
from datetime import datetime, timezone
from flask import Flask, Response, abort, request, redirect
from apscheduler.schedulers.background import BackgroundScheduler
from xml.etree import ElementTree as ET
from xml.dom import minidom # For pretty printing XML
import hashlib

# --- Configuration ---
DATA_DIR = "/app/data"  # Base directory for storing data
os.makedirs(DATA_DIR, exist_ok=True)  # Ensure data directory exists

# Cache file paths
CACHE_FILE = os.path.join(DATA_DIR, "stream_cache.json")
MPEGTS_CACHE_FILE = os.path.join(DATA_DIR, "mpegts_cache.json")

METADATA_API_URL = "https://ppv.wtf/api/streams" # For the main list
STREAM_DETAIL_URL_TEMPLATE = "https://ppvs.su/api/streams/{stream_id}" # For individual stream details
# Auth Token for API access
AUTH_TOKEN = os.environ.get("PPV_AUTH_TOKEN")
# How often to refresh data from the API (in seconds) - 3 hours = 10800 seconds
REFRESH_INTERVAL_SECONDS = 10800
# Port for the Flask service to run on
FLASK_PORT = 8880
# User-Agent for requests
USER_AGENT = "PlexRelay/1.0"
# Sports categories to include
SPORTS_CATEGORIES = ['NBA', 'NFL', 'MLB', 'NHL']

# --- Logging Setup ---
# Configure logging to output informational messages and errors with local timezone
logging.Formatter.converter = lambda *args: datetime.now(timezone.utc).astimezone().timetuple()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S %z'
)

# --- Globals for Caching and Scheduling ---
from threading import Lock # Import Lock for thread safety
cached_data = None # Stores the response from METADATA_API_URL
cached_mpegts_urls = {} # Cache for MPEG-TS URLs
last_fetch_time = 0 # Timestamp of the last successful fetch
fetch_lock = Lock() # Lock to ensure thread-safe access to shared resources
scheduler = BackgroundScheduler(daemon=True) # Runs fetch_and_cache_data periodically
app = Flask(__name__) # The Flask web application instance

# --- Helper Functions ---

def format_xmltv_time(unix_timestamp):
    """Converts Unix timestamp to XMLTV UTC time format (YYYYMMDDHHMMSS +0000)"""
    if not unix_timestamp:
        return "" # Return empty string if timestamp is missing
    try:
        # Convert the Unix timestamp (assumed UTC) to a datetime object
        dt_object = datetime.fromtimestamp(int(unix_timestamp), tz=timezone.utc)
        # Format the datetime object according to XMLTV standard (UTC)
        return dt_object.strftime('%Y%m%d%H%M%S +0000')
    except Exception as e:
        # Log any errors during timestamp conversion
        logging.error(f"Error formatting timestamp {unix_timestamp}: {e}")
        return "" # Return empty string on error

def load_from_cache():
    """Load cached data from disk at startup"""
    global cached_data, cached_mpegts_urls, last_fetch_time
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                cached_data = json.load(f)
            logging.info("Loaded stream cache from disk")
        
        if os.path.exists(MPEGTS_CACHE_FILE):
            with open(MPEGTS_CACHE_FILE, 'r') as f:
                cached_mpegts_urls = json.load(f)
            logging.info("Loaded MPEGTS cache from disk")
            
        if cached_data:
            last_fetch_time = os.path.getmtime(CACHE_FILE)
    except Exception as e:
        logging.error(f"Error loading cache files: {e}")

def get_mpegts_url(stream_id, auth_token):
    """
    Fetches the detailed stream information and extracts the MPEG-TS URL.
    Uses the endpoint format: https://ppv.wtf/api/streams/{stream_id}
    Expects the MPEG-TS URL in response['data']['vip_mpegts']
    """
    if not auth_token:
        logging.error(f"Auth token is missing. Cannot fetch MPEG-TS URL for stream {stream_id}.")
        return None # Indicate failure: no token provided

    # Construct the specific API endpoint URL for the given stream ID
    stream_api_url = STREAM_DETAIL_URL_TEMPLATE.format(stream_id=stream_id)
    logging.info(f"Attempting to fetch MPEG-TS URL for stream_id: {stream_id} from {stream_api_url}")

    # Prepare headers for the API request, including Auth and User-Agent
    headers = {
        "Auth": auth_token, # Changed from Authorization: Bearer to Auth
        "User-Agent": USER_AGENT
    }

    try:
        # Make the GET request to the stream detail API endpoint
        response = requests.get(stream_api_url, headers=headers, timeout=15) # Timeout set to 15 seconds
        response.raise_for_status() # Raise an HTTPError for bad status codes (4xx or 5xx)

        # --- Process the successful response ---
        data = response.json() # Parse the JSON response body

        # Check if the request was successful according to the API's own flag
        if data.get("success"):
            # Navigate the JSON structure to find the desired URL
            stream_data = data.get("data")
            if stream_data:
                mpegts_url = stream_data.get("vip_mpegts")
                if mpegts_url:
                    logging.info(f"Successfully fetched MPEG-TS URL for stream {stream_id}")
                    return mpegts_url
                else:
                    logging.warning(f"'vip_mpegts' key not found in API response data for stream {stream_id}.")
                    return None
            else:
                logging.warning(f"'data' key not found in API response for stream {stream_id}.")
                return None
        else:
            logging.error(f"API indicated failure for stream {stream_id}. Response: {data}")
            return None

    except requests.exceptions.Timeout:
        # Handle request timeout errors
        logging.error(f"Timeout error fetching MPEG-TS URL for stream {stream_id} from {stream_api_url}")
        return None
    except requests.exceptions.HTTPError as e:
        # Handle HTTP errors (like 401 Unauthorized, 404 Not Found, 5xx Server Error)
        logging.error(f"HTTP error fetching MPEG-TS URL for stream {stream_id}: {e.response.status_code} - {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        # Handle other general request errors (network issues, DNS errors)
        logging.error(f"Network error fetching MPEG-TS URL for stream {stream_id}: {e}")
        return None
    except Exception as e:
        # Handle unexpected errors (e.g., JSON parsing errors, logic errors)
        logging.error(f"Unexpected error fetching MPEG-TS URL for stream {stream_id}: {e}")
        return None


def fetch_and_cache_data():
    """Fetches the main stream list data from the metadata API and updates the cache."""
    global cached_data, last_fetch_time, cached_mpegts_urls

    try:
        logging.info("Fetching main stream list data from API...")
        headers = {
            "Auth": AUTH_TOKEN,
            "User-Agent": USER_AGENT
        }
        response = requests.get(METADATA_API_URL, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            cached_data = data
            last_fetch_time = time.time()
            cached_mpegts_urls = {}  # Clear MPEG-TS URL cache

            # Pre-fetch MPEG-TS URLs for all streams
            for category in cached_data.get('streams', []):
                for stream in category.get('streams', []):
                    stream_id = stream.get('id')
                    if stream_id:
                        mpegts_url = get_mpegts_url(stream_id, AUTH_TOKEN)
                        if mpegts_url:
                            cached_mpegts_urls[str(stream_id)] = mpegts_url

            # Save caches to disk
            try:
                with open(CACHE_FILE, 'w') as f:
                    json.dump(cached_data, f)
                with open(MPEGTS_CACHE_FILE, 'w') as f:
                    json.dump(cached_mpegts_urls, f)
                logging.info("Successfully saved cache files to disk")
            except Exception as e:
                logging.error(f"Error saving cache files: {e}")

            logging.info("Successfully updated cached data and MPEG-TS URLs.")
        else:
            logging.error(f"API response indicated failure: {data}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching main stream list data: {e}")
    except Exception as e:
        logging.error(f"Unexpected error during data fetch: {e}")


# --- Flask Routes ---

@app.route('/')
def index():
    """Provides a basic HTML status page for the service."""
    status = "OK"
    data_age = "No data cached"
    num_categories = 0
    num_streams = 0

    # Calculate how long ago the data was cached
    if last_fetch_time:
        age_seconds = int(time.time() - last_fetch_time)
        data_age = f"{age_seconds} seconds ago"

    # Count categories and streams if data is cached
    if cached_data and 'streams' in cached_data:
        num_categories = len(cached_data['streams'])
        num_streams = sum(len(cat.get('streams', [])) for cat in cached_data['streams'])
    elif not cached_data:
        status = "Error: Main stream list data not cached"

    # Check if the essential Auth Token is loaded
    auth_status = 'Yes' if AUTH_TOKEN else 'No - CRITICAL: Set PPV_AUTH_TOKEN environment variable!'

    # Return an HTML response with status information
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><title>Bridge Service Status</title></head>
    <body>
        <h1>Bridge Service Status</h1>
        <p>Status: {status}</p>
        <p>Last Main List Fetch: {data_age}</p>
        <p>Cached Categories: {num_categories}</p>
        <p>Cached Streams (in main list): {num_streams}</p>
        <p>Auth Token Loaded: {auth_status}</p>
        <hr>
        <p><a href="/playlist.m3u">M3U Playlist (/playlist.m3u)</a></p>
        <p><a href="/epg.xml">XMLTV EPG (/epg.xml)</a></p>
        <form action="/playlist.m3u">
            <button type="submit">Refresh M3U Playlist</button>
        </form>
        <form action="/epg.xml">
            <input type="hidden" name="force_refresh" value="1">
            <button type="submit">Refresh EPG</button>
        </form>
        <form action="/refresh">
            <button type="submit">Force Refresh EPG + M3U</button>
        </form>
    </body>
    </html>
    """
@app.route('/refresh')
def manual_refresh():
    """Manually triggers a refresh of the EPG and M3U playlist."""
    logging.info("Manual refresh requested, fetching main stream list data...")
    fetch_and_cache_data()
    return redirect('/')

@app.route('/playlist.m3u')
def generate_m3u():
    """Generates the M3U playlist dynamically."""
    if not cached_data:
        logging.warning("M3U requested but main list data not cached yet.")
        abort(503, "Data not available yet, please try again shortly.")
    if not AUTH_TOKEN:
         logging.error("M3U generation failed: Auth token missing.")
         abort(500, "Authentication token not configured on server.")

    m3u_content = ["#EXTM3U"]
    stream_count = 0

    categories = cached_data.get('streams', [])
    for category in categories:
        category_name = category.get('category', 'Unknown Category')
        streams = category.get('streams', [])
        for stream in streams:
            name = stream.get('name', '')
            start_time = stream.get('starts_at') or '0'
            base_string = f"{name}_{start_time}"
            tvg_id = str(int(hashlib.sha256(base_string.encode()).hexdigest(), 16) % 10**10)
            stream_name_slug = name.replace(' ', '_').lower()
            if not stream_name_slug:
                logging.warning(f"Skipping stream with missing name in category '{category_name}'. Data: {stream}")
                continue
            stream_name = name if name else f'Stream {tvg_id}'
            poster_url = stream.get('poster', '')
            # Log the tvg-id being used for debugging
            logging.debug(f"M3U: Adding stream '{stream_name}' with tvg-id='{tvg_id}'")

            stream_id = stream.get('id')
            mpegts_url = cached_mpegts_urls.get(str(stream_id)) if stream_id else None
            if mpegts_url:
                extinf_line = (
                    f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{stream_name}" '
                    f'tvg-logo="{poster_url}" group-title="{category_name}",{stream_name}'
                )
                m3u_content.append(extinf_line)
                m3u_content.append(mpegts_url)
                stream_count += 1
            else:
                logging.warning(f"No cached MPEG-TS URL found for stream ID {stream_id} ('{stream_name}'), skipping M3U entry.")

    logging.info(f"Generated M3U playlist with {stream_count} streams.")
    return Response('\n'.join(m3u_content), mimetype='application/vnd.apple.mpegurl')

@app.route('/epg.xml')
def generate_xmltv():
    """Generates the XMLTV EPG file dynamically."""
    if request.args.get('force_refresh'):
        fetch_and_cache_data()

    if not cached_data:
        logging.warning("XMLTV requested but main list data not cached yet.")
        abort(503, "Data not available yet, please try again shortly.")

    tv_root = ET.Element('tv', {'generator-info-name': 'PPVBridgeService/1.0'})

    response = Response(mimetype='application/xml')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    seen_channel_ids = set()
    programme_count = 0

    categories = cached_data.get('streams', [])
    for category in categories:
        streams = category.get('streams', [])
        for stream in streams:
            name = stream.get('name', '')
            start_time = stream.get('starts_at') or '0'
            base_string = f"{name}_{start_time}"
            channel_id = str(int(hashlib.sha256(base_string.encode()).hexdigest(), 16) % 10**10)
            stream_name_slug = name.replace(' ', '_').lower()
            if not stream_name_slug:
                logging.warning(f"Skipping EPG entry for stream with missing name in category '{category.get('category')}'. Data: {stream}")
                continue

            stream_name = name if name else f'Stream {channel_id}'
            poster_url = stream.get('poster', '')
            category_name = stream.get('category_name', category.get('category', 'Unknown'))
            tag = stream.get('tag', '')
            starts_at = stream.get('starts_at')
            ends_at = stream.get('ends_at')

            # Log the channel ID being used for debugging
            logging.debug(f"XMLTV: Adding channel '{stream_name}' with id='{channel_id}'")

            if channel_id not in seen_channel_ids:
                channel_el = ET.SubElement(tv_root, 'channel', {'id': channel_id})
                ET.SubElement(channel_el, 'display-name').text = stream_name
                if poster_url:
                    ET.SubElement(channel_el, 'icon', {'src': poster_url})
                seen_channel_ids.add(channel_id)

            start_time_str = format_xmltv_time(starts_at)
            end_time_str = format_xmltv_time(ends_at)

            if start_time_str and end_time_str:
                programme_el = ET.SubElement(tv_root, 'programme', {
                    'start': start_time_str,
                    'stop': end_time_str,
                    'channel': channel_id
                })
                ET.SubElement(programme_el, 'title', {'lang': 'en'}).text = stream_name
                description = f"{category_name}"
                if tag:
                    description += f" - {tag}"
                ET.SubElement(programme_el, 'desc', {'lang': 'en'}).text = description
                if poster_url:
                    ET.SubElement(programme_el, 'icon', {'src': poster_url})
                ET.SubElement(programme_el, 'category', {'lang': 'en'}).text = category_name
                programme_count += 1
            else:
                logging.warning(f"Skipping programme EPG entry for stream {channel_id} ('{stream_name}') due to missing/invalid start/end times.")

    rough_string = ET.tostring(tv_root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    logging.info(f"Generated XMLTV EPG with {len(seen_channel_ids)} channels and {programme_count} programmes.")
    response.data = pretty_xml
    return response

# --- Main Execution Block ---
if __name__ == '__main__':
    # Check for the essential auth token at startup
    if not AUTH_TOKEN:
        logging.error("CRITICAL: PPV_AUTH_TOKEN environment variable not set! Service may not function correctly.")

    # Load any existing cache from disk
    load_from_cache()

    # Perform an initial fetch of the main stream list if needed
    if not cached_data:
        logging.info("No cached data found, performing initial data fetch...")
        fetch_and_cache_data()
    else:
        logging.info("Loaded existing cache, scheduling next update...")

    # Schedule the background task to fetch the main stream list periodically
    scheduler.add_job(
        fetch_and_cache_data,
        'interval', # Run at regular intervals
        seconds=REFRESH_INTERVAL_SECONDS,
        id='api_fetch_job', # Job ID for management
        replace_existing=True # Overwrite if job already exists (e.g., on restart)
    )
    scheduler.start() # Start the background scheduler
    logging.info(f"Scheduler started. Fetching main stream list every {REFRESH_INTERVAL_SECONDS} seconds.")

    # Start the Flask web server
    # Use host='0.0.0.0' to make it accessible from outside the Docker container
    logging.info(f"Starting Flask server on http://0.0.0.0:{FLASK_PORT}")
    app.run(host='0.0.0.0', port=FLASK_PORT)

    # Attempt graceful shutdown of the scheduler when the app exits
    # Note: This might not always execute if the app is killed forcefully
    try:
        logging.info("Attempting to shut down scheduler...")
        scheduler.shutdown()
    except Exception as e:
        logging.info(f"Scheduler shutdown error (may be normal on forced exit): {e}")

