import os
from dropbox import Dropbox
from datetime import datetime, timedelta
import requests
from threading import Lock
import json

def log_print(message):
    print(message, flush=True)

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
            log_print(f"Attempting to refresh token with data: {json.dumps(data, default=str)}")
            response = requests.post('https://api.dropboxapi.com/oauth2/token', data=data)
            log_print(f"Token refresh response status: {response.status_code}")
            log_print(f"Token refresh response content: {response.text}")
            response.raise_for_status()
            token_info = response.json()
            
            self.access_token = token_info['access_token']
            self.token_expiration = datetime.now() + timedelta(seconds=token_info['expires_in'])
            log_print("Access token refreshed successfully")
        except requests.exceptions.RequestException as e:
            log_print(f"Error refreshing access token: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                log_print(f"Error response content: {e.response.text}")
            raise
        except Exception as e:
            log_print(f"Unexpected error refreshing access token: {str(e)}")
            raise
