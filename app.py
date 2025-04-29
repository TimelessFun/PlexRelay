import os
import requests
import time
import logging
from datetime import datetime, timezone
from flask import Flask, Response, abort, request
from apscheduler.schedulers.background import BackgroundScheduler
from xml.etree import ElementTree as ET
from xml.dom import minidom # For pretty printing XML

# --- Configuration ---
METADATA_API_URL = "https://ppv.wtf/api/streams" # For the main list
STREAM_DETAIL_URL_TEMPLATE = "https://ppv.wtf/api/streams/{stream_id}" # For individual stream details
# Auth Token for API access
AUTH_TOKEN = os.environ.get("PPV_AUTH_TOKEN")
# How often to refresh data from the API (in seconds) - 6 hours = 21600 seconds
REFRESH_INTERVAL_SECONDS = 21600
# Port for the Flask service to run on
FLASK_PORT = 8880
# User-Agent for requests
USER_AGENT = "PlexRelay/1.0"
# Sports categories to include
SPORTS_CATEGORIES = ['NBA', 'NFL', 'MLB', 'NHL']

# --- Logging Setup ---
# Configure logging to output informational messages and errors
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            # Use .get() for safer access to nested dictionaries
            stream_data = data.get("data")
            if stream_data:
                mpegts_url = stream_data.get("vip_mpegts") # Extract the URL
                if mpegts_url:
                    logging.info(f"Successfully fetched MPEG-TS URL for stream {stream_id}")
                    return mpegts_url # Return the found URL
                else:
                    # Log if 'vip_mpegts' key is missing in the 'data' object
                    logging.warning(f"'vip_mpegts' key not found in API response data for stream {stream_id}.")
                    return None
            else:
                # Log if 'data' key is missing in the main response object
                logging.warning(f"'data' key not found in API response for stream {stream_id}.")
                return None
        else:
            # Log if the API response indicates failure (success: false)
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
    # Use a lock to prevent concurrent fetches, ensuring data consistency
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
        # Sum up the number of streams in each category
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
    </body>
    </html>
    """

@app.route('/playlist.m3u')
def generate_m3u():
    """Generates the M3U playlist dynamically."""
    # Check if essential data and token are available
    if not cached_data:
        logging.warning("M3U requested but main list data not cached yet.")
        abort(503, "Data not available yet, please try again shortly.") # Service Unavailable
    if not AUTH_TOKEN:
         logging.error("M3U generation failed: Auth token missing.")
         abort(500, "Authentication token not configured on server.") # Internal Server Error

    m3u_content = ["#EXTM3U"] # Start with the required M3U header
    stream_count = 0 # Counter for successfully added streams

    categories = cached_data.get('streams', [])
    # Iterate through each category and its streams from the cached main list
    for category in categories:
        category_name = category.get('category', 'Unknown Category')
        streams = category.get('streams', [])
        for stream in streams:
            stream_id = stream.get('id')
            stream_name = stream.get('name', f'Stream {stream_id}')
            poster_url = stream.get('poster', '')
            # Use stream ID as tvg-id for reliable EPG mapping in clients like Plex/XTeVe
            tvg_id = str(stream_id) if stream_id else ""

            # Skip streams that don't have an ID in the main list data
            if not stream_id:
                logging.warning(f"Skipping stream with missing ID in category '{category_name}'. Data: {stream}")
                continue

            # Use cached MPEG-TS URL
            mpegts_url = cached_mpegts_urls.get(str(stream_id))
            if mpegts_url:
                extinf_line = (
                    f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{stream_name}" '
                    f'tvg-logo="{poster_url}" group-title="{category_name}",{stream_name}'
                )
                m3u_content.append(extinf_line)
                m3u_content.append(mpegts_url) # Add the stream URL
                stream_count += 1
            else:
                logging.warning(f"No cached MPEG-TS URL found for stream ID {stream_id} ('{stream_name}'), skipping M3U entry.")

    logging.info(f"Generated M3U playlist with {stream_count} streams.")
    return Response('\n'.join(m3u_content), mimetype='application/vnd.apple.mpegurl')


@app.route('/epg.xml')
def generate_xmltv():
    """Generates the XMLTV EPG file dynamically."""
    # Check if the main stream list data is cached
    if not cached_data:
        logging.warning("XMLTV requested but main list data not cached yet.")
        abort(503, "Data not available yet, please try again shortly.") # Service Unavailable

    # Create the root <tv> element for the XMLTV document
    tv_root = ET.Element('tv', {'generator-info-name': 'PPVBridgeService/1.0'})
    seen_channel_ids = set() # Keep track of channel IDs already added
    programme_count = 0 # Counter for programme entries added

    categories = cached_data.get('streams', [])
    # Iterate through categories and streams from the cached main list
    for category in categories:
        streams = category.get('streams', [])
        for stream in streams:
            # Extract stream details needed for EPG
            stream_id = stream.get('id')
            stream_name = stream.get('name', f'Stream {stream_id}')
            poster_url = stream.get('poster', '')
            category_name = stream.get('category_name', category.get('category', 'Unknown'))
            tag = stream.get('tag', '')
            starts_at = stream.get('starts_at') # Unix timestamp
            ends_at = stream.get('ends_at') # Unix timestamp

            # Skip entries without a stream ID
            if not stream_id:
                logging.warning(f"Skipping EPG entry for stream with missing ID in category '{category_name}'. Data: {stream}")
                continue

            channel_id = str(stream_id) # Use stream ID as the channel ID for mapping

            # Add the <channel> element to the XML if not already added
            if channel_id not in seen_channel_ids:
                channel_el = ET.SubElement(tv_root, 'channel', {'id': channel_id})
                ET.SubElement(channel_el, 'display-name').text = stream_name
                if poster_url: # Add icon if available
                    ET.SubElement(channel_el, 'icon', {'src': poster_url})
                seen_channel_ids.add(channel_id) # Mark channel as added

            # Add the <programme> element for the specific event/stream time
            start_time_str = format_xmltv_time(starts_at) # Format start time
            end_time_str = format_xmltv_time(ends_at) # Format end time

            # Only add the programme entry if both start and end times are valid
            if start_time_str and end_time_str:
                programme_el = ET.SubElement(tv_root, 'programme', {
                    'start': start_time_str,
                    'stop': end_time_str,
                    'channel': channel_id # Link programme to its channel ID
                })
                # Add programme details
                ET.SubElement(programme_el, 'title', {'lang': 'en'}).text = stream_name
                description = f"{category_name}" # Start description with category
                if tag:
                    description += f" - {tag}" # Append tag if present
                ET.SubElement(programme_el, 'desc', {'lang': 'en'}).text = description
                if poster_url: # Add icon if available
                    ET.SubElement(programme_el, 'icon', {'src': poster_url})
                ET.SubElement(programme_el, 'category', {'lang': 'en'}).text = category_name
                # Add other elements like episode-num, rating, etc. if available/needed
                programme_count += 1
            else:
                 # Log if a programme entry is skipped due to time issues
                 logging.warning(f"Skipping programme EPG entry for stream {stream_id} ('{stream_name}') due to missing/invalid start/end times.")

    # Convert the ElementTree structure to a nicely formatted XML string
    rough_string = ET.tostring(tv_root, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    # Log the result of EPG generation
    logging.info(f"Generated XMLTV EPG with {len(seen_channel_ids)} channels and {programme_count} programmes.")
    # Return the XML content with the correct MIME type
    return Response(pretty_xml, mimetype='application/xml')

# --- Main Execution Block ---
if __name__ == '__main__':
    # Check for the essential auth token at startup
    if not AUTH_TOKEN:
        logging.error("CRITICAL: PPV_AUTH_TOKEN environment variable not set! Service may not function correctly.")
        # Allowing the service to start to show the status page error,
        # but M3U generation will fail.

    # Perform an initial fetch of the main stream list immediately on startup
    logging.info("Performing initial data fetch on startup...")
    fetch_and_cache_data()

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

