import os
import sys
import logging
from flask import Flask, request, jsonify, make_response
import requests
import fitz  # PyMuPDF
import json
import hmac
import hashlib

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Retrieve environment variables
DROPBOX_APP_SECRET = os.environ.get('dropbox_app_token')
DROPBOX_TOKEN = os.environ.get('dropbox_token')

# Check for required environment variables
if not DROPBOX_APP_SECRET:
    logger.error("DROPBOX_APP_SECRET (dropbox_app_token) is not set")
    sys.exit(1)
if not DROPBOX_TOKEN:
    logger.error("DROPBOX_TOKEN (dropbox_token) is not set")
    sys.exit(1)

def verify_webhook_request(request):
    signature = request.headers.get('X-Dropbox-Signature')
    if not signature:
        logger.warning("No X-Dropbox-Signature in request headers")
        return False

    body = request.data

    computed_signature = hmac.new(
        DROPBOX_APP_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, signature)

@app.route('/')
def home():
    logger.info("Home route accessed")
    return "Webhook receiver is running!"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        logger.info(f'Received GET request. Args: {request.args}')
        challenge = request.args.get('challenge')
        if challenge:
            logger.info(f"Challenge received: {challenge}")
            response = make_response(challenge)
            response.headers['Content-Type'] = 'text/plain'
            logger.info(f"Sending response: {response.get_data(as_text=True)}")
            return response
        logger.warning("No challenge received")
        return "No challenge received", 400

    elif request.method == 'POST':
        logger.info(f"Received POST request. Headers: {request.headers}")
        if not verify_webhook_request(request):
            logger.warning("Invalid webhook signature")
            return jsonify({"status": "error", "message": "Invalid request signature"}), 403

        try:
            request_json = request.json
            logger.info(f"Request JSON: {request_json}")
            if 'list_folder' in request_json and 'entries' in request_json['list_folder']:
                for entry in request_json['list_folder']['entries']:
                    if entry['.tag'] == 'file':
                        file_path = entry['path_lower']
                        headers = {
                            "Authorization": f"Bearer {DROPBOX_TOKEN}",
                            "Dropbox-API-Arg": json.dumps({"path": file_path})
                        }
                        download_url = "https://content.dropboxapi.com/2/files/download"
                        response = requests.post(download_url, headers=headers)
                        
                        if response.status_code == 200:
                            local_file_path = f"/tmp/{os.path.basename(file_path)}"
                            with open(local_file_path, 'wb') as f:
                                f.write(response.content)
                            
                            qa_result = dropbox_qa(local_file_path)
                            
                            os.remove(local_file_path)
                            
                            return jsonify({"status": "success", "qa_result": qa_result}), 200
                        else:
                            logger.error(f"Failed to download file: {response.status_code}")
                            return jsonify({"status": "error", "message": "Failed to download file"}), 400
            
            logger.warning("No file path provided in the webhook payload")
            return jsonify({"status": "error", "message": "No file path provided"}), 400
        except Exception as e:
            logger.exception(f"Error processing webhook: {str(e)}")
            return jsonify({"status": "error", "message": "Internal server error"}), 500

def is_close_to_color(color, target_color, threshold=0.1):
    distance = sum((a - b) ** 2 for a, b in zip(color, target_color)) ** 0.5
    return distance < threshold

def is_magenta(color):
    r, g, b = color
    return r > 0.5 and b > 0.5 and g < 0.3

def dropbox_qa(pdf):
    target_color = (0.9260547757148743, 0.0, 0.548302412033081)
    document = fitz.open(pdf)
    count = 0
    for page_num in range(len(document)):
        page = document.load_page(page_num)
        for item in page.get_drawings():
            if 'color' in item:
                if is_close_to_color(item['color'], target_color) and is_magenta(item['color']):
                    count += 1
    return f'{count} instances of magenta lines with vector paths'

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 8080))
        logger.info(f"Starting application on port {port}")
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        logger.exception(f"Failed to start the application: {str(e)}")
        sys.exit(1)
