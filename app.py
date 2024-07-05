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

@app.route('/')
def home():
    return "Webhook receiver is running!"

DROPBOX_APP_SECRET = os.environ.get('dropbox_app_token')

def verify_webhook_request(request):
    if DROPBOX_APP_SECRET is None:
        raise ValueError("DROPBOX_APP_SECRET environment variable is not set")

    signature = request.headers.get('X-Dropbox-Signature')
    if not signature:
        return False

    body = request.data

    # Compute the HMAC-SHA256 using the app secret
    computed_signature = hmac.new(
        DROPBOX_APP_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()

    # Compare the computed signature with the one provided in the request
    return hmac.compare_digest(computed_signature, signature)
@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        logging.debug(f"Received GET request. Args: {request.args}")
        # Handle the webhook verification challenge
        challenge = request.args.get('challenge')
        if challenge:
            logging.debug(f"Challenge received: {challenge}")
            response = make_response(challenge)
            response.headers['Content-Type'] = 'text/plain'
            logging.debug(f"Sending response: {response.get_data(as_text=True)}")
        logging.warning("No challenge received")
        return "No challenge received", 400

    elif request.method == 'POST':
        logging.debug("Received POST request")
        request_json = request.json  # Get JSON data from the request
        if 'list_folder' in request_json and 'entries' in request_json['list_folder']:
            for entry in request_json['list_folder']['entries']:
                if entry['.tag'] == 'file':
                    file_path = entry['path_lower']
                    dropbox_token = os.environ.get('DROPBOX_TOKEN')
                    headers = {
                        "Authorization": f"Bearer {dropbox_token}",
                        "Dropbox-API-Arg": json.dumps({"path": file_path})
                    }
                    download_url = "https://content.dropboxapi.com/2/files/download"
                    response = requests.post(download_url, headers=headers)
                    
                    if response.status_code == 200:
                        local_file_path = f"/tmp/{os.path.basename(file_path)}"
                        with open(local_file_path, 'wb') as f:
                            f.write(response.content)
                        
                        qa_result = dropbox_qa(local_file_path)
                        
                        # Clean up: delete the temporary file
                        os.remove(local_file_path)
                        
                        return jsonify({"status": "success", "qa_result": qa_result}), 200
                    else:
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
    app.run(debug=True, port=int(os.getenv("PORT", default=5000)))
