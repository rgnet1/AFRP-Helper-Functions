import os
from typing import Optional
from dotenv import load_dotenv

class MagazineConfig:
    """Centralized configuration for magazine processing system."""
    
    def __init__(self):
        # Check if running in Docker
        self.in_docker = os.environ.get('DOCKER_CONTAINER', False)
        # self.base_path = '/app' if self.in_docker else '.'
        self.base_path = './'
        
        # Load .env from config directory
        load_dotenv(f'{self.base_path}/config/.env')
        
        # Dropbox settings
        self.dropbox_client_id = self._get_env("DROPBOX_CLIENT_ID")
        self.dropbox_client_secret = self._get_env("DROPBOX_CLIENT_SECRET")
        self.dropbox_folder_path = '/hathihe ramallah'
        
        # Server settings
        self.server_ip = "192.168.2.11"
        self.server_user = "root"
        self.server_password = self._get_env("SERVER_PASSWORD", required=False)
        self.server_path = "/mnt/user/Ramzey/AFRP Archive/Magazine-Issues-2022-Present/"
        
        # Email/SMS settings
        self.email = self._get_env("EMAIL")
        self.email_password = self._get_env("EMAIL_APP_PASSWORD")
        self.notification_numbers = {
            key: number for key, number in {
                "primary": self._get_env("PHONE_NUMBER"),
                "secondary": self._get_env("PHONE_NUMBER_TWO", required=False)
            }.items() if number
        }
        
        # File paths
        self.download_path = f"{self.base_path}/downloads"
        self.metadata_file = f"{self.base_path}/config/last_downloaded_file.json"
        # Ensure logs directory exists
        os.makedirs(f"{self.base_path}/logs", exist_ok=True)
        self.log_file = f"{self.base_path}/logs/magazine.log"

    def _get_env(self, key: str, required: bool = True) -> Optional[str]:
        """Get environment variable with optional requirement check.
        
        Args:
            key: Environment variable key
            required: Whether the variable is required (raises error if missing)
            
        Returns:
            The environment variable value or None if not required and not found
            
        Raises:
            ValueError: If required variable is missing
        """
        value = os.getenv(key)
        if required and not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value

    @property
    def dropbox_credentials_valid(self) -> bool:
        """Check if required Dropbox credentials are present."""
        return bool(self.dropbox_client_id and self.dropbox_client_secret)

    @property
    def notification_credentials_valid(self) -> bool:
        """Check if required notification credentials are present."""
        return bool(self.email and self.email_password)
