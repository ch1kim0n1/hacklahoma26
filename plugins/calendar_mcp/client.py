from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# SCOPES are additive — add more as you support more services
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]

def get_google_service(api_name, api_version, credentials_path, token_path):
    credentials_path = Path(credentials_path)
    token_path = Path(token_path)

    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path,
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())

    return build(api_name, api_version, credentials=creds)