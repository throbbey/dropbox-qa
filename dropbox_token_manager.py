import os
import time
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
        self.last_request_time = 0
        self.min_request_interval = 1  # Minimum 1 second between requests

        if not all([self.app_key, self.app_secret, self.refresh_token]):
            raise ValueError("DROPBOX_APP_KEY, DROPBOX_APP_SECRET, and DROPBOX_REFRESH_TOKEN must be set in environment variables")

    def get_client(self):
        with self.lock:
            if self.access_token is None or self.token_expiration is None or datetime.now() >= self.token_expiration:
                self.refresh_access_token()
            return Dropbox(self.access_token, session=self.rate_limited_session())

    def rate_limited_session(self):
        class RateLimitedSession(requests.Session):
            def request(self, *args, **kwargs):
                current_time = time.time()
                if current_time - self.last_request_time < self.min_request_interval:
                    time.sleep(self.min_request_interval - (current_time - self.last_request_time))
                self.last_request_time = time.time()
                return super(RateLimitedSession, self).request(*args, **kwargs)

        session = RateLimitedSession()
        session.last_request_time = self.last_request_time
        session.min_request_interval = self.min_request_interval
        return session

    def refresh_access_token(self):
        try:
            log_print("Attempting to refresh access token...")
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': self.refresh_token,
                'client_id': self.app_key,
                'client_secret': self.app_secret
            }
            response = requests.post('https://api.dropboxapi.com/oauth2/token', data=data)
            log_print(f"Token refresh response status: {response.status_code}")
            
            if response.status_code != 200:
                log_print(f"Error response content: {response.text}")
                response.raise_for_status()
            
            token_info = response.json()
            self.access_token = token_info['access_token']
            # Set expiration to slightly less than the actual expiration time to be safe
            self.token_expiration = datetime.now() + timedelta(seconds=token_info['expires_in'] - 300)
            log_print("Access token refreshed successfully")
        except requests.exceptions.RequestException as e:
            log_print(f"Error refreshing access token: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                log_print(f"Error response content: {e.response.text}")
            raise
        except Exception as e:
            log_print(f"Unexpected error refreshing access token: {str(e)}")
            raise

    def test_connection(self):
        try:
            dbx = self.get_client()
            account = dbx.users_get_current_account()
            log_print(f"Successfully connected to Dropbox. Account: {account.name.display_name}")
            return True
        except Exception as e:
            log_print(f"Error connecting to Dropbox: {str(e)}")
            return False
