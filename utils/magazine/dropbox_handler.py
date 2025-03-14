import dropbox
import os
import logging
import json
import time
from typing import Optional, List, Dict, Any
from dropbox.files import FileMetadata
from utils.magazine.config import MagazineConfig
from utils.magazine.generate_dropbox_token import save_token, load_token, generate_token, refresh_token

class DropboxHandler:
    """Handles all Dropbox-related operations for magazine processing."""
    
    def __init__(self, config: MagazineConfig):
        """Initialize DropboxHandler with configuration.
        
        Args:
            config: MagazineConfig instance containing necessary settings
        """
        self.config = config
        self.dbx = self._initialize_dropbox()

    def _initialize_dropbox(self) -> dropbox.Dropbox:
        """Initialize and return authenticated Dropbox client.
        
        Returns:
            Authenticated Dropbox client instance
            
        Raises:
            ValueError: If Dropbox credentials are invalid
        """
        if not self.config.dropbox_credentials_valid:
            raise ValueError("Dropbox credentials not properly configured")
            
        access_token = self._get_access_token()
        dbx = dropbox.Dropbox(access_token)
        
        # Verify the access token
        account = dbx.users_get_current_account()
        logging.info(f"Account verification successful. User: {account.name.display_name}")
        
        return dbx

    def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token string
            
        Raises:
            TypeError: If token is not in expected format
            KeyError: If access token is missing
        """
        token = load_token()
        
        if not isinstance(token, dict):
            logging.error("Loaded token is not a dictionary")
            raise TypeError("Loaded token is not a dictionary")
        
        # logging.debug(f"Loaded token: {token}")
        logging.info(f"Loaded Dropbox token\n")

        if 'access_token' not in token:
            logging.error("Access token is missing from the loaded token")
            raise KeyError("Access token is missing from the token")

        # Refresh token if needed
        if 'expires_at' not in token or token['expires_at'] <= time.time():
            logging.info("Refreshing access token...")
            token = refresh_token()

        if not isinstance(token, dict):
            logging.error("Refreshed token is not a dictionary")
            raise TypeError("Refreshed token is not a dictionary")
        
        return token['access_token']

    def list_files(self) -> List[FileMetadata]:
        """List all files in the configured Dropbox folder.
        
        Returns:
            List of Dropbox FileMetadata objects
        """
        try:
            result = self.dbx.files_list_folder(self.config.dropbox_folder_path)
            files = [entry for entry in result.entries if isinstance(entry, dropbox.files.FileMetadata)]
            return files
        except dropbox.exceptions.ApiError as err:
            logging.error(f"API error during file listing: {err}")
            print(f"API error: {err}", flush=True)
            return []

    def find_latest_file(self, files: List[FileMetadata]) -> Optional[FileMetadata]:
        """Find the most recently modified file in the list.
        
        Args:
            files: List of Dropbox FileMetadata objects
            
        Returns:
            Most recently modified FileMetadata or None if no files
        """
        if not files:
            logging.info("No files found in the folder")
            return None

        latest_file = max(files, key=lambda x: x.client_modified)
        logging.info(f"Latest file found: {latest_file.name}, modified at {latest_file.client_modified}\n")
        return latest_file

    def download_file(self, file_metadata: FileMetadata) -> Optional[str]:
        """Download the specified file to the configured download path.
        
        Args:
            file_metadata: Dropbox FileMetadata object for file to download
            
        Returns:
            Local file path if download successful, None otherwise
        """
        file_path = file_metadata.path_display
        local_file_path = os.path.join(self.config.download_path, os.path.basename(file_path))
        
        try:
            with open(local_file_path, "wb") as f:
                metadata, res = self.dbx.files_download(path=file_path)
                f.write(res.content)
                logging.info(f"Downloaded {file_path} to {local_file_path}\n")
                print(f"Downloaded {file_path} to {local_file_path}\n", flush=True)

            self._save_download_metadata(file_metadata)
            return local_file_path

        except dropbox.exceptions.AuthError as auth_error:
            logging.error(f"Authentication error during file download: {auth_error}\n")
            print(f"Authentication error during file download: {auth_error}\n", flush=True)
        except Exception as e:
            logging.error(f"Failed to download {file_path}: {e}\n")
            print(f"Failed to download {file_path}: {e}\n", flush=True)
        
        return None

    def _save_download_metadata(self, file_metadata: FileMetadata) -> None:
        """Save metadata about downloaded file.
        
        Args:
            file_metadata: Dropbox FileMetadata object for downloaded file
        """
        with open(self.config.metadata_file, 'w') as metadata_file:
            json.dump({
                'path': file_metadata.path_display,
                'id': file_metadata.id
            }, metadata_file)

    def get_last_downloaded_file(self) -> Optional[Dict[str, str]]:
        """Retrieve metadata of the last downloaded file.
        
        Returns:
            Dictionary with file metadata or None if no previous download
        """
        if os.path.exists(self.config.metadata_file):
            with open(self.config.metadata_file, 'r') as metadata_file:
                last_file_metadata = json.load(metadata_file)
                logging.info(f"Loaded last downloaded file metadata: {last_file_metadata}")
                
                if not isinstance(last_file_metadata, dict):
                    logging.error("Last downloaded file metadata is not a dictionary")
                    raise TypeError("Last downloaded file metadata is not a dictionary")
                
                return last_file_metadata
        return None

    def process_latest_file(self) -> Optional[str]:
        """Process the latest file by downloading if newer than last download.
        
        Returns:
            Path to downloaded file if successful and newer, None otherwise
        """
        files = self.list_files()
        latest_file = self.find_latest_file(files)

        if latest_file:
            last_downloaded = self.get_last_downloaded_file()
            if last_downloaded and last_downloaded['id'] == latest_file.id:
                logging.info("The latest file has already been downloaded")
                print("The latest file has already been downloaded", flush=True)
                return None
            else:
                return self.download_file(latest_file)
        return None
