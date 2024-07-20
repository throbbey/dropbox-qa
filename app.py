import os
import sys
import traceback
from flask import Flask, jsonify, request
import logging
from threading import Thread

from dropbox_token_manager import DropboxTokenManager, log_print

# Initialize Flask app
app = Flask(__name__)

# Initialize DropboxTokenManager
token_manager = None

def init_token_manager():
    global token_manager
    token_manager = DropboxTokenManager()
    return token_manager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

@app.route('/')
def home():
    return "Dropbox QA Service is running."

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

def run_qa_process():
    log_print("Starting QA process...")
    try:
        global token_manager
        if token_manager is None:
            token_manager = init_token_manager()
        dbx = token_manager.get_client()
        # ... rest of your QA process ...
        return {"message": "QA process completed successfully"}
    except Exception as e:
        error_msg = f"An error occurred during QA process: {e}"
        log_print(error_msg)
        return {"error": error_msg}

if __name__ == "__main__":
    try:
        log_print("Starting application...")
        port = int(os.environ.get("PORT", 8080))
        log_print(f"Using port: {port}")
        
        # Initialize and check Dropbox connection
        token_manager = init_token_manager()
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
