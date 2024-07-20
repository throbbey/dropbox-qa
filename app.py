import os
import sys
import traceback
import dropbox
import json
from datetime import datetime, timedelta
import fitz  # PyMuPDF
from flask import Flask, jsonify, request
import logging
from threading import Thread, Lock
from dropbox_token_manager import DropboxTokenManager, log_print

# Initialize Flask app
app = Flask(__name__)

# Initialize DropboxTokenManager
token_manager = DropboxTokenManager()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

DOWNLOAD_FOLDER = 'downloads'
processed_files = set()
processed_files_lock = Lock()

def list_recent_uploads(dbx):
    result = dbx.files_list_folder('')
    sorted_entries = sorted(result.entries, key=lambda entry: entry.server_modified, reverse=True)
    
    cut_pdf_files = [
        entry for entry in sorted_entries 
        if isinstance(entry, dropbox.files.FileMetadata) 
        and "CUT" in entry.name.upper() 
        and entry.name.lower().endswith('.pdf')
        and entry.name not in processed_files
    ]
    
    return cut_pdf_files

@app.route('/')
def home():
    return "Dropbox QA Service is running."

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

def upload_qa_result(dbx, file_path, qa_result, status):
    file_name = os.path.basename(file_path)
    qa_file_name = f"{status}_{file_name}_qa_result.txt"
    qa_file_path = os.path.join(DOWNLOAD_FOLDER, qa_file_name)
    
    # Create QA result file
    with open(qa_file_path, 'w') as f:
        f.write(f"{status}\n")
        f.write(f"QA Result: {qa_result}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}")
    
    # Upload QA result file
    with open(qa_file_path, 'rb') as f:
        try:
            dbx.files_upload(f.read(), f"/{qa_file_name}", mode=dropbox.files.WriteMode.overwrite)
            log_print(f"QA result uploaded successfully as {qa_file_name}")
        except Exception as e:
            log_print(f"Error uploading QA result: {e}")

def is_close_to_color(color, target_color, threshold=0.1):
    if color is None or len(color) != 3:
        return False
    distance = sum((a - b) ** 2 for a, b in zip(color, target_color)) ** 0.5
    return distance < threshold

def is_magenta(color):
    if color is None or len(color) != 3:
        return False
    r, g, b = color
    return r > 0.5 and b > 0.5 and g < 0.3

def process_qa(dbx, entry):
    if not entry.name.lower().endswith('.pdf'):
        log_print(f"Skipping non-PDF file: {entry.name}")
        return None, None

    local_path = download_file(dbx, entry)
    if not local_path:
        log_print(f"Failed to download {entry.name}")
        return None, None

    try:
        document = fitz.open(local_path)
    except Exception as e:
        log_print(f"Error opening PDF file {entry.name}: {e}")
        return None, None

    target_color = (0.9260547757148743, 0.0, 0.548302412033081)
    count = 0
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        for item in page.get_drawings():
            if 'color' in item and item['color'] is not None:
                if is_close_to_color(item['color'], target_color) and is_magenta(item['color']):
                    count += 1
    document.close()

    qa_result = f'{count} instances of magenta lines with vector paths'
    status = "FAIL" if count == 0 else "PASS"
    log_print(f"QA Result for {entry.name}: {status} - {qa_result}")
    
    upload_qa_result(dbx, local_path, qa_result, status)
    return status, qa_result

@app.route('/run-qa')
def run_qa():
    result = run_qa_process()
    return jsonify(result)

def run_qa_process():
    log_print("Starting QA process...")
    try:
        dbx = token_manager.get_client()
        cut_files = list_recent_uploads(dbx)
        
        if not cut_files:
            log_print("No new files to process.")
            return {"message": "No new files to process."}
        
        results = []
        for entry in cut_files:
            with processed_files_lock:
                if entry.name in processed_files:
                    continue
                processed_files.add(entry.name)
            
            log_print(f"Processing file: {entry.name}")
            status, qa_result = process_qa(dbx, entry)
            if status is not None and qa_result is not None:
                results.append({
                    "filename": entry.name,
                    "status": status,
                    "result": qa_result
                })
        
        log_print(f"QA process completed for {len(results)} new files.")
        return {
            "message": f"QA process completed for {len(results)} new files.",
            "results": results
        }
    except Exception as e:
        error_msg = f"An error occurred during QA process: {e}"
        log_print(error_msg)
        log_print(f"Error details: {traceback.format_exc()}")
        return {"error": error_msg}

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
        
        # Test Dropbox connection
        if token_manager.test_connection():
            log_print("Successfully connected to Dropbox")
        else:
            log_print("Failed to connect to Dropbox")
        
        log_print("Initializing Flask app...")
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        error_msg = f"Error starting the application: {e}\n{traceback.format_exc()}"
        log_print(error_msg)
        # Write to a file as a last resort
        with open('startup_error.log', 'w') as f:
            f.write(error_msg)
        sys.exit(1)
