import os
import requests
from dotenv import load_dotenv
import logging

class SharePointHandler:
    def __init__(self):
        self.tenant_id = os.getenv("AZURE_TENANT_ID")
        self.client_id = os.getenv("AZURE_CLIENT_ID")
        self.client_secret = os.getenv("AZURE_CLIENT_SECRET")
        self.site_id = os.getenv("SHAREPOINT_SITE_ID")
        self.drive_id = os.getenv("SHAREPONT_DRIVE_ID")
        self.access_token = None

    def authenticate(self):
        """Authenticate with Microsoft Graph API."""
        auth_url = f'https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token'
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'https://graph.microsoft.com/.default'
        }
        response = requests.post(auth_url, data=data)
        if response.status_code == 200:
            self.access_token = response.json().get('access_token')
            logging.info("SharePoint authentication successful.")
            print("SharePoint authentication successful.")
        else:
            raise Exception(f"SharePoint authentication failed: {response.status_code}, {response.text}")

    def file_exists(self, destination_dir, file_name):
        """Check if a file already exists in SharePoint."""
        check_url = (f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/"
                     f"{self.drive_id}/root:/{destination_dir}/{file_name}")
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        response = requests.get(check_url, headers=headers)
        if response.status_code == 200:
            logging.info(f"File '{file_name}' already exists in '{destination_dir}'.")
            return True
        elif response.status_code == 404:
            return False
        else:
            raise Exception(f"Error checking file existence: {response.status_code}, {response.text}")

    def upload_file(self, local_file_path, destination_dir):
        """Upload a file to SharePoint if it does not already exist."""
        file_name = os.path.basename(local_file_path)

        # Check if file exists before uploading
        if self.file_exists(destination_dir, file_name):
            print("Sharepoint: SKIPPING UPLOAD")
            logging.info(f"Sharepoint: Skipping upload. File '{file_name}' already exists in '{destination_dir}'.")
            return

        upload_url = (f"https://graph.microsoft.com/v1.0/sites/{self.site_id}/drives/"
                      f"{self.drive_id}/root:/{destination_dir}/{file_name}:/content")
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/octet-stream'
        }
        with open(local_file_path, 'rb') as file:
            response = requests.put(upload_url, headers=headers, data=file)
        if response.status_code in (200, 201):
            print(f"File uploaded to SharePoint: {file_name}")
            logging.info(f"File uploaded to SharePoint: {file_name}")
        else:
            raise Exception(f"SharePoint upload failed: {response.status_code}, {response.text}")



def upload_file_to_sharepoint(local_file_path, destination_dir):
    """Upload a file to SharePoint."""
    uploader = SharePointHandler()
    try:
        uploader.authenticate()
        uploader.upload_file(local_file_path, destination_dir)
    except Exception as e:
        print(f"Error: {e}")
        logging.error(f"Error: {e}")

# Example usage
if __name__ == "__main__":
    load_dotenv(dotenv_path="./config/.env")
    uploader = SharePointHandler()
    
    try:
        uploader.authenticate()
        print("DONE AUTHENTICATING")
        uploader.upload_file("./downloads/Vol74-No2_2025-Mar-Apr_HathiheRamallah_web.pdf", "2025")
    except Exception as e:
        print(f"Error: {e}")
