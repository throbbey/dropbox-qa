import os
import dropbox
import json
from datetime import datetime
import fitz  # PyMuPDF
from flask import Flask, jsonify

APP_KEY = os.getenv('APP_KEY')
APP_SECRET = os.getenv('APP_SECRET')
DROPBOX_ACCESS_TOKEN = os.getenv('DROPBOX_ACCESS_TOKEN')
DOWNLOAD_FOLDER = 'downloads'

if not DROPBOX_ACCESS_TOKEN:
    raise ValueError("DROPBOX_ACCESS_TOKEN must be set in .env file or environment variables")

app = Flask(__name__)

def get_dropbox_client():
    return dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)

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
    
    print(f"Downloading {entry.name}...")
    
    with open(local_path, 'wb') as f:
        metadata, response = dbx.files_download(entry.path_display)
        f.write(response.content)
    
    print(f"File downloaded successfully to {local_path}")
    return local_path

def upload_qa_result(dbx, file_path, qa_result, status):
    file_name = os.path.basename(file_path)
    qa_file_name = f"{file_name}_qa_result.txt"
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
            print(f"QA result uploaded successfully as {qa_file_name}")
        except Exception as e:
            print(f"Error uploading QA result: {e}")



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
        print(f"Skipping non-PDF file: {entry.name}")
        return

    local_path = download_file(dbx, entry)
    if not local_path:
        print(f"Failed to download {entry.name}")
        return

    try:
        document = fitz.open(local_path)
    except Exception as e:
        print(f"Error opening PDF file {entry.name}: {e}")
        return

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
    status = "PASS" if count == 0 else "FAIL"
    print(f"QA Result for {entry.name}: {status} - {qa_result}")
    
    upload_qa_result(dbx, local_path, qa_result, status)
    return status, qa_result

@app.route('/')
def home():
    return "Dropbox QA Service is running."

@app.route('/run-qa')
def run_qa():
    try:
        dbx = get_dropbox_client()
        cut_files = list_recent_uploads(dbx)
        
        if not cut_files:
            return jsonify({"message": "No files to process."}), 200
        
        results = []
        for entry in cut_files:
            status, qa_result = process_qa(dbx, entry)
            results.append({
                "filename": entry.name,
                "status": status,
                "result": qa_result
            })
        
        return jsonify({
            "message": "QA process completed for all CUT files.",
            "results": results
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
