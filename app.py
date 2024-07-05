from flask import Flask, request, jsonify, make_response
import os
import requests
import fitz  # PyMuPDF
import json
import hmac
import hashlib
import logging

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

DROPBOX_APP_SECRET = os.environ.get('dropbox_app_token')
DROPBOX_TOKEN = os.environ.get('dropbox_token')

def verify_webhook_request(request):
    if not DROPBOX_APP_SECRET:
        app.logger.error("DROPBOX_APP_SECRET environment variable is not set")
        return False

    signature = request.headers.get('X-Dropbox-Signature')
    if not signature:
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
    return "Webhook receiver is running!"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        app.logger.info(f'Received GET request. Args: {request.args}')
        challenge = request.args.get('challenge')
        if challenge:
            app.logger.info(f"Challenge received: {challenge}")
            response = make_response(challenge)
            response.headers['Content-Type'] = 'text/plain'
            app.logger.info(f"Sending response: {response.get_data(as_text=True)}")
            return response
        app.logger.warning("No challenge received")
        return "No challenge received", 400

    elif request.method == 'POST':
        app.logger.info("Received POST request")
        if not verify_webhook_request(request):
            app.logger.warning("Invalid webhook signature")
            return jsonify({"status": "error", "message": "Invalid request signature"}), 403

        request_json = request.json
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
                        app.logger.error(f"Failed to download file: {response.status_code}")
                        return jsonify({"status": "error", "message": "Failed to download file"}), 400
    
        return jsonify({"status": "error", "message": "No file path provided"}), 400

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
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
