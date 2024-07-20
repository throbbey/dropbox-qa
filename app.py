import os
from dropbox import Dropbox
from dropbox import DropboxOAuth2FlowNoRedirect
from datetime import datetime, timedelta
import requests
from threading import Lock

class DropboxTokenManager:
    def __init__(self):
        self.app_key = os.getenv('DROPBOX_APP_KEY')
        self.app_secret = os.getenv('DROPBOX_APP_SECRET')
        self.refresh_token = os.getenv('DROPBOX_REFRESH_TOKEN')
        self.access_token = None
        self.token_expiration = None
        self.lock = Lock()

    def get_client(self):
        with self.lock:
            if self.access_token is None or datetime.now() >= self.token_expiration:
                self.refresh_access_token()
            return Dropbox(self.access_token)

    def refresh_access_token(self):
        try:
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.app_key,
                'client_secret': self.app_secret
            }
            response = requests.post('https://api.dropboxapi.com/oauth2/token', data=data)
            response.raise_for_status()
            token_info = response.json()
            
            self.access_token = token_info['access_token']
            self.token_expiration = datetime.now() + timedelta(seconds=token_info['expires_in'])
            log_print("Access token refreshed successfully")
        except Exception as e:
            log_print(f"Error refreshing access token: {e}")
            raise

def get_refresh_token():
    app_key = os.getenv('DROPBOX_APP_KEY')
    app_secret = os.getenv('DROPBOX_APP_SECRET')
    
    auth_flow = DropboxOAuth2FlowNoRedirect(app_key, app_secret)
    authorize_url = auth_flow.start()
    print("1. Go to: " + authorize_url)
    print("2. Click \"Allow\" (you might have to log in first).")
    print("3. Copy the authorization code.")
    auth_code = input("Enter the authorization code here: ").strip()

    try:
        oauth_result = auth_flow.finish(auth_code)
        print("Refresh token:", oauth_result.refresh_token)
        return oauth_result.refresh_token
    except Exception as e:
        print('Error: %s' % (e,))
        return None

# Usage in your main application
token_manager = DropboxTokenManager()

# Example usage in your QA process
def run_qa_process():
    log_print("Starting QA process...")
    try:
        dbx = token_manager.get_client()
        # ... rest of your QA process ...
    except Exception as e:
        error_msg = f"An error occurred during QA process: {e}"
        log_print(error_msg)
        return {"error": error_msg}

# ... rest of your application code ...
