import os
import sys
import traceback
import dropbox
from dropbox import DropboxOAuth2Flow
import json
from datetime import datetime, timedelta
import fitz  # PyMuPDF
from flask import Flask, jsonify, request
import logging
from threading import Thread, Lock

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def log_print(message):
    print(message, flush=True)
    logger.info(message)

APP_KEY = os.getenv('DROPBOX_APP_KEY')
APP_SECRET = os.getenv('DROPBOX_APP_SECRET')
REFRESH_TOKEN = os.getenv('DROPBOX_REFRESH_TOKEN')
DOWNLOAD_FOLDER = 'downloads'

if not all([APP_KEY, APP_SECRET, REFRESH_TOKEN]):
    raise ValueError("DROPBOX_APP_KEY, DROPBOX_APP_SECRET, and DROPBOX_REFRESH_TOKEN must be set in environment variables")

app = Flask(__name__)

class DropboxTokenManager:
    def __init__(self):
        self.access_token = None
        self.token_expiration = None
        self.lock = Lock()

    def get_client(self):
        with self.lock:
            if self.access_token is None or datetime.now() >= self.token_expiration:
                self.refresh_access_token()
            return dropbox.Dropbox(self.access_token)

    def refresh_access_token(self):
        try:
            flow = DropboxOAuth2Flow(
                APP_KEY,
                APP_SECRET,
                'http://localhost:8080',  # This is just a placeholder
                None,
                'dropbox-auth-csrf-token'
            )
            oauth_result = flow.finish({'refresh_token': REFRESH_TOKEN})
            self.access_token = oauth_result.access_token
            self.token_expiration = datetime.now() + timedelta(seconds=oauth_result.expires_in)
            log_print("Access token refreshed successfully")
        except Exception as e:
            log_print(f"Error refreshing access token: {e}")
            raise

token_manager = DropboxTokenManager()

def list_recent_uploads(dbx):
    result = dbx.files_list_folder('')
    sorted_entries = sorted(result.entries, key=lambda entry: entry.server_modified, reverse=True)
    
    cut_pdf_files = [
        entry for entry in sorted_entries 
        if isinstance(entry, dropbox.files.FileMetadata) 
        and "CUT" in entry.name.upper() 
        and entry.name.lower().endswith('.pdf')
    ]
    
    return cut_pdf_files

def download_file(dbx, entry):
    if not os.path.exists(DOWNLOAD_FOLDER):
        os.makedirs(DOWNLOAD_FOLDER)
    
    local_path = os.path.join(DOWNLOAD_FOLDER, entry.name)
    
    log_print(f"Downloading {entry.name}...")
    
    try:
        with open(local_path, 'wb') as f:
            metadata, response = dbx.files_download(entry.path_display)
            f.write(response.content)
        
        log_print(f"File downloaded successfully to {local_path}")
        return local_path
    except dropbox.exceptions.ApiError as e:
        log_print(f"Error downloading file: {e}")
        return None

# ... [rest of your existing functions] ...

def run_qa_process():
    log_print("Starting QA process...")
    try:
        dbx = token_manager.get_client()
        cut_files = list_recent_uploads(dbx)
        
        if not cut_files:
            log_print("No files to process.")
            return {"message": "No files to process."}
        
        results = []
        for entry in cut_files:
            local_path = download_file(dbx, entry)
            if local_path:
                status, qa_result = process_qa(dbx, entry)
                if status is not None and qa_result is not None:
                    results.append({
                        "filename": entry.name,
                        "status": status,
                        "result": qa_result
                    })
            else:
                log_print(f"Failed to download {entry.name}")
        
        log_print(f"QA process completed for {len(results)} out of {len(cut_files)} CUT files.")
        return {
            "message": f"QA process completed for {len(results)} out of {len(cut_files)} CUT files.",
            "results": results
        }
    except Exception as e:
        error_msg = f"An error occurred during QA process: {e}"
        log_print(error_msg)
        return {"error": error_msg}

@app.route('/run-qa')
def run_qa():
    result = run_qa_process()
    return jsonify(result)
    
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    log_print(f"Webhook accessed with method: {request.method}")
    log_print(f"Request args: {request.args}")
    if request.method == 'GET':
        challenge = request.args.get('challenge', '')
        log_print(f"Responding to challenge: {challenge}")
        return challenge
    elif request.method == 'POST':
        log_print("Received webhook notification")
        log_print(f"Request data: {request.data}")
        # Trigger QA process in a separate thread
        Thread(target=run_qa_process).start()
        return jsonify(success=True)

if __name__ == "__main__":
    try:
        log_print("Starting application...")
        port = int(os.environ.get("PORT", 8080))
        log_print(f"Using port: {port}")
        
        # Check if we can connect to Dropbox
        try:
            dbx = token_manager.get_client()
            dbx.users_get_current_account()
            log_print("Successfully connected to Dropbox")
        except Exception as e:
            log_print(f"Error connecting to Dropbox: {e}")
        
        log_print("Initializing Flask app...")
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        error_msg = f"Error starting the application: {e}\n{traceback.format_exc()}"
        log_print(error_msg)
        # Write to a file as a last resort
        with open('startup_error.log', 'w') as f:
            f.write(error_msg)
        sys.exit(1)
