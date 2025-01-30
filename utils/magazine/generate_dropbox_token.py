import os
import json
import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth2Session
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

# Load environment variables
load_dotenv('/config/.env')

# Disable the HTTPS requirement for OAuthlib (only for local development)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Dropbox OAuth 2.0 client settings
CLIENT_ID = os.getenv("DROPBOX_CLIENT_ID")
CLIENT_SECRET = os.getenv("DROPBOX_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080"  # Use localhost for development

# Dropbox OAuth 2.0 endpoints
AUTHORIZATION_BASE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

# File to store the access token
TOKEN_FILE = '/config/dropbox_token.json'

def save_token(token):
    """Save OAuth token to a file."""
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token, f)

def load_token():
    """Load OAuth token from a file."""
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            try:
                token = json.load(f)
                
                # Log the type and content of the token to debug
                logging.info(f"Loaded token content: {token}")
                logging.info(f"Type of loaded token: {type(token)}")
                
                if not isinstance(token, dict):
                    logging.error("Loaded token is not a dictionary. Possible corruption or incorrect format.")
                    raise TypeError("Loaded token is not a dictionary.")
                return token
            except json.JSONDecodeError as json_err:
                logging.error(f"Error decoding JSON from token file: {json_err}")
                raise ValueError("Token file contains invalid JSON.")
    return None



class OAuthHTTPServer(HTTPServer):
    """Custom HTTP server to store authorization response."""
    def __init__(self, *args, **kwargs):
        self.authorization_response = None
        super().__init__(*args, **kwargs)

def generate_token():
    """Generate a new OAuth token via user authorization."""
    scope = ['files.metadata.read', 'files.content.read', 'account_info.read']

    oauth = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=scope)

    authorization_url, state = oauth.authorization_url(AUTHORIZATION_BASE_URL, token_access_type='offline')
    print(f"Go to the following URL to authorize the application:\n{authorization_url}")

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            query = self.path.split('?', 1)[-1]
            self.server.authorization_response = f"http://localhost:8080?{query}"
            self.wfile.write(b"<html><body><h1>You may close this window.</h1></body></html>")

    webbrowser.open(authorization_url)
    httpd = OAuthHTTPServer(('localhost', 8080), RequestHandler)
    httpd.handle_request()

    authorization_response = httpd.authorization_response

    token = oauth.fetch_token(
        TOKEN_URL,
        authorization_response=authorization_response,
        client_secret=CLIENT_SECRET,
        include_client_id=True
    )

    save_token(token)
    verify_token(token['access_token'])

    return token


def refresh_token():
    """Refresh the access token using the refresh token."""
    token = load_token()
    if not token:
        logging.error("No token found during refresh; generating new token.")
        return generate_token()

    refresh_token = token.get('refresh_token')
    if not refresh_token:
        logging.error("No refresh token found; generating new token.")
        return generate_token()

    payload = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }

    response = requests.post(TOKEN_URL, data=payload)
    
    logging.info(f"Refresh token response content: {response.content}")

    if response.status_code != 200:
        logging.error(f"Failed to refresh token: {response.text}")
        return generate_token()

    try:
        new_token = response.json()
        logging.info(f"Parsed new token: {new_token}")
    except json.JSONDecodeError as json_err:
        logging.error(f"JSON decode error: {json_err}")
        raise ValueError("Failed to decode the token response as JSON.")

    # Ensure the new_token is a dictionary
    if not isinstance(new_token, dict):
        logging.error(f"Refreshed token is not a dictionary. Received type: {type(new_token)}")
        raise TypeError("Refreshed token is not a dictionary.")

    # Add the refresh token back if it's not in the new token
    new_token['refresh_token'] = refresh_token

    # Save and reload the token to ensure integrity
    save_token(new_token)
    saved_token = load_token()
    
    if not isinstance(saved_token, dict):
        logging.error("Reloaded token after saving is not a dictionary.")
        raise TypeError("Reloaded token after saving is not a dictionary.")

    return saved_token





def verify_token(access_token):
    """Verify the retrieved access token by making a simple API call."""
    try:
        dbx = dropbox.Dropbox(access_token)
        account = dbx.users_get_current_account()
        print(f"Access token is valid for user: {account.name.display_name}")
    except dropbox.exceptions.AuthError as auth_error:
        print(f"AuthError during token verification: {auth_error}")
