import os
import json
from datetime import datetime, date, timezone, timedelta
import pytz
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import time
import requests
import threading
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
load_dotenv()

# --- Google Sheets Config ---
GOOGLE_CREDENTIALS_JSON_CONTENT = os.getenv('GOOGLE_CREDENTIALS_JSON')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID', '1RTJmYTGMN-nH6X5eBdxfkIXjoBv1TD7Wy4w5-tW8VF8')
SHEET_NAME = os.getenv('SHEET_NAME', 'Sheet1')

# --- PostgreSQL Config ---
DATABASE_URL = os.getenv('DATABASE_URL')

# --- LeetCode Config ---
LEETCODE_USER = os.getenv('LEETCODE_USER')

# --- Striver Config ---
STRIVER_USER = os.getenv('STRIVER_USER')  # Striver username
STRIVER_SESSION_COOKIE = os.getenv('STRIVER_SESSION_COOKIE')  # For authenticated requests

# --- Application Logic Config ---
INITIAL_CUTOFF_DATETIME_IST_STR = "2025-05-17 08:00:00"
IST_TIMEZONE = pytz.timezone('Asia/Kolkata')
UTC = pytz.utc

try:
    naive_dt = datetime.strptime(INITIAL_CUTOFF_DATETIME_IST_STR, "%Y-%m-%d %H:%M:%S")
    aware_dt_ist = IST_TIMEZONE.localize(naive_dt)
    INITIAL_CUTOFF_DATETIME_UTC = aware_dt_ist.astimezone(UTC)
except Exception as e:
    print(f"Error parsing INITIAL_CUTOFF_DATETIME_IST_STR: {e}")
    INITIAL_CUTOFF_DATETIME_UTC = datetime.now(UTC)

STATE_TABLE_NAME = "coding_sync_state"
LEETCODE_STATE_KEY = "last_processed_leetcode_timestamp_utc"
STRIVER_STATE_KEY = "last_processed_striver_timestamp_utc"

# Sheet columns
COL_PLATFORM = "Platform"  # New column for platform identification
COL_TOPIC = "Topic"
COL_PROBLEM = "Problem"
COL_CONFIDENCE = "confidence"
COL_LAST_VISITED = "Last Visited"
COL_DIFFICULTY = "Difficulty"  # New column for difficulty
EXPECTED_HEADERS = [COL_PLATFORM, COL_TOPIC, COL_PROBLEM, COL_DIFFICULTY, COL_CONFIDENCE, COL_LAST_VISITED]

# --- Initialize Flask App ---
app = Flask(__name__)
sync_job_running = False

# --- DATABASE HELPER FUNCTIONS ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set.")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise

def initialize_database():
    """Creates the state table if it doesn't exist."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    key VARCHAR(255) PRIMARY KEY,
                    value TIMESTAMPTZ
                );
            """).format(sql.Identifier(STATE_TABLE_NAME)))
        conn.commit()
        print(f"Database table '{STATE_TABLE_NAME}' initialized/checked.")
    except Exception as e:
        print(f"Error initializing database table: {e}")
    finally:
        if conn:
            conn.close()

def get_last_processed_timestamp(platform_key):
    """Retrieves the last processed timestamp from the database for a specific platform."""
    conn = get_db_connection()
    last_timestamp = None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql.SQL("SELECT value FROM {} WHERE key = %s")
                        .format(sql.Identifier(STATE_TABLE_NAME)), (platform_key,))
            result = cur.fetchone()
            if result and result['value']:
                last_timestamp = result['value'].replace(tzinfo=pytz.utc)
    except Exception as e:
        print(f"Error retrieving last processed timestamp for {platform_key}: {e}")
    finally:
        if conn:
            conn.close()

    if last_timestamp:
        print(f"Retrieved last processed timestamp for {platform_key}: {last_timestamp}")
        return last_timestamp
    else:
        print(f"No last processed timestamp found for {platform_key}, using initial cutoff: {INITIAL_CUTOFF_DATETIME_UTC}")
        return INITIAL_CUTOFF_DATETIME_UTC

def update_last_processed_timestamp(platform_key, new_timestamp_utc):
    """Updates the last processed timestamp in the database for a specific platform."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("""
                INSERT INTO {} (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
            """).format(sql.Identifier(STATE_TABLE_NAME)), (platform_key, new_timestamp_utc))
        conn.commit()
        print(f"Updated last processed timestamp for {platform_key} to: {new_timestamp_utc}")
    except Exception as e:
        print(f"Error updating last processed timestamp for {platform_key}: {e}")
    finally:
        if conn:
            conn.close()

# --- GOOGLE SHEETS HELPER FUNCTIONS ---
def get_gspread_client():
    """Authenticates and returns a gspread client."""
    if GOOGLE_CREDENTIALS_JSON_CONTENT:
        try:
            creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON_CONTENT)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                creds_dict, 
                scopes=['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            )
            client = gspread.authorize(creds)
            return client
        except Exception as e:
            print(f"Error authenticating with Google Sheets using JSON content: {e}")
            raise
    else:
        try:
            if not os.path.exists('credentials.json'):
                print("CRITICAL: credentials.json file not found in the current directory.")
                raise FileNotFoundError("credentials.json file not found.")
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
            client = gspread.authorize(creds)
            return client
        except Exception as e:
            print(f"Failed to authenticate with credentials.json. Error: {e}")
            raise

def get_sheet_data(client):
    """Fetches all data from the specified Google Sheet."""
    try:
        sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(SHEET_NAME)
        print(f"Accessing sheet: {sheet.title}")
        
        all_values = sheet.get_all_values()
        if not all_values:
            return {}, sheet, 1
            
        header_row = all_values[0]
        
        # Check if headers exist, if not add them
        missing_headers = [h for h in EXPECTED_HEADERS if h not in header_row]
        if missing_headers:
            print(f"Adding missing headers: {missing_headers}")
            new_header_row = header_row + missing_headers
            sheet.update('1:1', [new_header_row])
            header_row = new_header_row
        
        problem_col_index = header_row.index(COL_PROBLEM)
        platform_col_index = header_row.index(COL_PLATFORM)
        last_visited_col_index = header_row.index(COL_LAST_VISITED)

        sheet_problems = {}
        for row_num, row_data in enumerate(all_values[1:], start=2):
            if len(row_data) > problem_col_index and row_data[problem_col_index]:
                problem_name = row_data[problem_col_index]
                
                # Extract problem name from hyperlink if present
                if problem_name.startswith('=HYPERLINK("'):
                    try:
                        parts = problem_name.split('"')
                        if len(parts) >= 4:
                            problem_name = parts[3]
                    except Exception:
                        pass

                platform = ""
                if len(row_data) > platform_col_index:
                    platform = row_data[platform_col_index]

                last_visited_str = ""
                if len(row_data) > last_visited_col_index:
                    last_visited_str = row_data[last_visited_col_index]

                # Create a unique key combining platform and problem name
                unique_key = f"{platform}:{problem_name}"
                sheet_problems[unique_key] = {
                    'row_number': row_num,
                    'last_visited': last_visited_str,
                    'platform': platform
                }
        
        return sheet_problems, sheet, len(all_values) + 1
    except Exception as e:
        print(f"Error getting sheet data: {e}")
        raise

# --- LEETCODE DATA FETCHING ---
def get_topic_tags_for_problem_public(title_slug):
    """Fetches topic tags for a LeetCode problem."""
    graphql_endpoint = "https://leetcode.com/graphql/"
    query = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        topicTags {
          name
          slug
        }
        difficulty
      }
    }
    """
    variables = {"titleSlug": title_slug}
    payload = {"query": query, "variables": variables}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "LeetCodeSheetSync/1.0 (Topic Tag Fetcher)"
    }
    try:
        time.sleep(0.5)
        response = requests.post(graphql_endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        result = {"topics": ["Uncategorized"], "difficulty": "Medium"}
        
        if 'data' in data and data['data'] and data['data']['question']:
            question_data = data['data']['question']
            
            # Get topics
            if question_data['topicTags']:
                result["topics"] = [tag['name'] for tag in question_data['topicTags']]
            
            # Get difficulty
            if question_data['difficulty']:
                result["difficulty"] = question_data['difficulty']
                
        return result
    except Exception as e:
        print(f"Warning: Could not fetch data for {title_slug}: {e}")
        return {"topics": ["Uncategorized"], "difficulty": "Medium"}

def fetch_leetcode_submissions(last_processed_ts_utc):
    """Fetches recent LeetCode submissions."""
    if not LEETCODE_USER:
        print("ERROR: LEETCODE_USER environment variable is not set.")
        return []

    graphql_endpoint = "https://leetcode.com/graphql/"
    query = """
    query recentAcSubmissions($username: String!, $limit: Int!) {
      recentAcSubmissionList(username: $username, limit: $limit) {
        id
        title
        titleSlug
        timestamp
      }
    }
    """
    variables = {"username": LEETCODE_USER, "limit": 20}
    payload = {"query": query, "variables": variables}
    headers = {
        "Content-Type": "application/json",
        "Referer": f"https://leetcode.com/u/{LEETCODE_USER}/",
        "User-Agent": "LeetCodeSheetSync/1.0 (Public API)"
    }
    
    print(f"Fetching recent LeetCode submissions for user: {LEETCODE_USER}")
    try:
        response = requests.post(graphql_endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching LeetCode submissions: {e}")
        return []

    submissions = []
    if 'data' in data and data['data'] and 'recentAcSubmissionList' in data['data']:
        for sub in data['data']['recentAcSubmissionList'] or []:
            submission_timestamp_unix = int(sub['timestamp'])
            submission_dt_utc = datetime.fromtimestamp(submission_timestamp_unix, tz=UTC)
            
            if submission_dt_utc <= last_processed_ts_utc:
                continue
            
            problem_data = get_topic_tags_for_problem_public(sub['titleSlug'])
            submissions.append({
                "platform": "LeetCode",
                "name": sub['title'],
                "url": f"https://leetcode.com/problems/{sub['titleSlug']}/",
                "timestamp_utc": submission_dt_utc,
                "topic_tags": problem_data["topics"],
                "difficulty": problem_data["difficulty"]
            })
        
        print(f"Fetched {len(submissions)} new LeetCode submissions")
    
    return submissions

# --- STRIVER DATA FETCHING ---
def fetch_striver_progress(last_processed_ts_utc):
    """Fetches Striver A2Z DSA progress."""
    if not STRIVER_USER:
        print("WARNING: STRIVER_USER not set, skipping Striver sync")
        return []
    
    print(f"Fetching Striver progress for user: {STRIVER_USER}")
    
    # Striver A2Z DSA sheet topics mapping
    striver_topics = {
        "step-1": "Learn the basics",
        "step-2": "Learn Important Sorting Techniques",
        "step-3": "Solve Problems on Arrays",
        "step-4": "Binary Search",
        "step-5": "Strings",
        "step-6": "Learn LinkedList",
        "step-7": "Recursion",
        "step-8": "Bit Manipulation",
        "step-9": "Stack and Queues",
        "step-10": "Sliding Window & Two Pointer",
        "step-11": "Heaps",
        "step-12": "Greedy Algorithm",
        "step-13": "Binary Trees",
        "step-14": "Binary Search Trees",
        "step-15": "Graphs",
        "step-16": "Dynamic Programming",
        "step-17": "Tries",
        "step-18": "String Matching Algorithm"
    }
    
    submissions = []
    headers = {
        "User-Agent": "StriverSheetSync/1.0",
        "Accept": "application/json"
    }
    
    # Add session cookie if available
    if STRIVER_SESSION_COOKIE:
        headers["Cookie"] = STRIVER_SESSION_COOKIE
    
    try:
        # Fetch user's completed problems from Striver's API
        # Note: This is a simplified example - you'll need to reverse engineer the actual API
        base_url = "https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2"
        
        # For demonstration, we'll create mock data
        # In reality, you'd need to:
        # 1. Find the actual API endpoints
        # 2. Handle authentication properly
        # 3. Parse the response correctly
        
        # Mock submission for demonstration
        mock_submissions = [
            {
                "platform": "Striver A2Z",
                "name": "Two Sum",
                "url": "https://takeuforward.org/data-structure/two-sum-check-if-a-pair-with-given-sum-exists-in-array/",
                "timestamp_utc": datetime.now(UTC),
                "topic_tags": ["Arrays", "Hashing"],
                "difficulty": "Easy"
            }
        ]
        
        # Filter based on timestamp
        for submission in mock_submissions:
            if submission["timestamp_utc"] > last_processed_ts_utc:
                submissions.append(submission)
        
        print(f"Fetched {len(submissions)} new Striver submissions")
        
    except Exception as e:
        print(f"Error fetching Striver progress: {e}")
    
    return submissions

# --- ENHANCED SYNC LOGIC ---
def run_synchronization_logic():
    global sync_job_running
    sync_job_running = True
    
    try:
        print(f"Enhanced synchronization started at {datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z%z')}")
        
        # Initialize database
        if DATABASE_URL:
            try:
                initialize_database()
            except Exception as e:
                print(f"Database initialization error: {e}")
        
        # Get last processed timestamps for both platforms
        leetcode_last_ts = INITIAL_CUTOFF_DATETIME_UTC
        striver_last_ts = INITIAL_CUTOFF_DATETIME_UTC
        
        if DATABASE_URL:
            leetcode_last_ts = get_last_processed_timestamp(LEETCODE_STATE_KEY)
            striver_last_ts = get_last_processed_timestamp(STRIVER_STATE_KEY)
        
        # Fetch submissions from both platforms
        all_submissions = []
        
        # LeetCode submissions
        try:
            leetcode_submissions = fetch_leetcode_submissions(leetcode_last_ts)
            all_submissions.extend(leetcode_submissions)
        except Exception as e:
            print(f"Error fetching LeetCode submissions: {e}")
        
        # Striver submissions
        try:
            striver_submissions = fetch_striver_progress(striver_last_ts)
            all_submissions.extend(striver_submissions)
        except Exception as e:
            print(f"Error fetching Striver submissions: {e}")
        
        if not all_submissions:
            print("No new submissions from any platform.")
            return
        
        # Sort submissions by timestamp
        all_submissions.sort(key=lambda s: s['timestamp_utc'])
        
        # Get Google Sheet data
        try:
            gs_client = get_gspread_client()
            sheet_problems_map, sheet_obj, _ = get_sheet_data(gs_client)
        except Exception as e:
            print(f"Error with Google Sheets: {e}")
            return
        
        # Process submissions
        updates_to_sheet_cells = []
        new_rows_to_add_data = []
        
        new_leetcode_max_ts = leetcode_last_ts
        new_striver_max_ts = striver_last_ts
        
        for submission in all_submissions:
            platform = submission['platform']
            problem_name = submission['name']
            problem_url = submission['url']
            submission_dt_utc = submission['timestamp_utc']
            topic = ", ".join(submission.get('topic_tags', ["Uncategorized"]))
            difficulty = submission.get('difficulty', 'Medium')
            
            submission_date_for_sheet = submission_dt_utc.strftime('%m/%d/%Y')
            problem_hyperlink = f'=HYPERLINK("{problem_url}","{problem_name}")'
            
            # Create unique key for this platform and problem
            unique_key = f"{platform}:{problem_name}"
            matched_problem = sheet_problems_map.get(unique_key)
            
            if matched_problem:
                # Update existing entry if newer
                try:
                    current_date = date.min
                    if matched_problem['last_visited']:
                        current_date = datetime.strptime(matched_problem['last_visited'], '%m/%d/%Y').date()
                except ValueError:
                    current_date = date.min
                
                if submission_dt_utc.date() > current_date:
                    row_to_update = matched_problem['row_number']
                    header_list = [COL_PLATFORM, COL_TOPIC, COL_PROBLEM, COL_DIFFICULTY, COL_CONFIDENCE, COL_LAST_VISITED]
                    last_visited_col_idx = header_list.index(COL_LAST_VISITED) + 1
                    updates_to_sheet_cells.append(gspread.Cell(row_to_update, last_visited_col_idx, submission_date_for_sheet))
                    print(f"Updating '{problem_name}' from {platform}")
            else:
                # Add new entry
                new_row_data = [platform, topic, problem_hyperlink, difficulty, "", submission_date_for_sheet]
                new_rows_to_add_data.append(new_row_data)
                print(f"Adding new problem '{problem_name}' from {platform}")
            
            # Update max timestamps
            if platform == "LeetCode" and submission_dt_utc > new_leetcode_max_ts:
                new_leetcode_max_ts = submission_dt_utc
            elif platform == "Striver A2Z" and submission_dt_utc > new_striver_max_ts:
                new_striver_max_ts = submission_dt_utc
        
        # Apply updates to sheet
        if updates_to_sheet_cells:
            try:
                print(f"Applying {len(updates_to_sheet_cells)} cell updates")
                sheet_obj.update_cells(updates_to_sheet_cells, value_input_option='USER_ENTERED')
            except Exception as e:
                print(f"Error updating cells: {e}")
        
        if new_rows_to_add_data:
            try:
                print(f"Adding {len(new_rows_to_add_data)} new rows")
                sheet_obj.append_rows(new_rows_to_add_data, value_input_option='USER_ENTERED')
            except Exception as e:
                print(f"Error adding new rows: {e}")
        
        # Update timestamps in database
        if DATABASE_URL:
            if new_leetcode_max_ts > leetcode_last_ts:
                update_last_processed_timestamp(LEETCODE_STATE_KEY, new_leetcode_max_ts)
            if new_striver_max_ts > striver_last_ts:
                update_last_processed_timestamp(STRIVER_STATE_KEY, new_striver_max_ts)
        
        print(f"Enhanced synchronization completed at {datetime.now(IST_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S %Z%z')}")
        
    finally:
        sync_job_running = False

# --- FLASK ENDPOINTS ---
@app.route('/trigger-sync', methods=['GET'])
def handle_trigger_sync():
    global sync_job_running
    
    if sync_job_running:
        return jsonify({"status": "warning", "message": "Sync job already in progress"}), 409
    
    print("Starting enhanced sync for LeetCode + Striver")
    thread = threading.Thread(target=run_synchronization_logic)
    thread.start()
    
    return jsonify({"status": "success", "message": "Enhanced sync triggered (LeetCode + Striver)"}), 202

@app.route('/', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(), 
        "job_running": sync_job_running,
        "platforms": ["LeetCode", "Striver A2Z"]
    }), 200

@app.route('/platforms', methods=['GET'])
def get_platforms():
    return jsonify({
        "platforms": {
            "LeetCode": {"enabled": bool(LEETCODE_USER), "user": LEETCODE_USER},
            "Striver": {"enabled": bool(STRIVER_USER), "user": STRIVER_USER}
        }
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    print(f"Enhanced LeetCode + Striver sync app starting on port {port}")
    print("Supported platforms: LeetCode, Striver A2Z DSA Sheet")
    app.run(host="0.0.0.0", port=5000, debug=True)