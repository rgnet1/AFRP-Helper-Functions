import os
from typing import List, Optional
from dotenv import load_dotenv

class MagazineConfig:
    """Centralized configuration for magazine processing system."""
    
    def __init__(self):
        # Check if running in Docker
        self.in_docker = os.environ.get('DOCKER_CONTAINER', False)
        self.base_path = '/app' if self.in_docker else '.'
        self.config_path = '/config' if self.in_docker else f"{self.base_path}/config"
        
        # Load .env from config directory
        load_dotenv(self.config_path)
        
        # Dropbox settings
        self.dropbox_client_id = self._get_env("DROPBOX_CLIENT_ID")
        self.dropbox_client_secret = self._get_env("DROPBOX_CLIENT_SECRET")
        self.dropbox_folder_path = '/hathihe ramallah'
        
        # Server settings
        self.server_ip = "192.168.2.11"
        self.server_user = "root"
        self.server_password = self._get_env("SERVER_PASSWORD", required=False)
        self.server_path = "/mnt/user/Ramzey/AFRP Archive/Magazine-Issues-2022-Present/"
        
        # Notification settings (optional until a channel is enabled in NOTIFY_CHANNELS)
        self.notify_channels = [name.lower() for name in self._get_list("NOTIFY_CHANNELS")]
        self.ntfy_topic = self._get_env("NTFY_TOPIC", required=False)
        self.ntfy_server = self._get_env("NTFY_SERVER", required=False) or "https://ntfy.sh"
        self.email = self._get_env("EMAIL", required=False)
        self.email_password = self._get_env("EMAIL_APP_PASSWORD", required=False)
        self.notify_emails = self._get_list("NOTIFY_EMAILS")
        self.telegram_bot_token = self._get_env("TELEGRAM_BOT_TOKEN", required=False)
        self.telegram_chat_ids = self._get_list("TELEGRAM_CHAT_IDS")
        self.discord_webhook_url = self._get_env("DISCORD_WEBHOOK_URL", required=False)
        
        # File paths
        self.download_path = f"{self.base_path}/downloads"
        self.metadata_file = f"{self.config_path}/last_downloaded_file.json"
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

    def _get_list(self, key: str) -> List[str]:
        """Split a comma-separated environment variable into stripped items."""
        value = os.getenv(key, "")
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def dropbox_credentials_valid(self) -> bool:
        """Check if required Dropbox credentials are present."""
        return bool(self.dropbox_client_id and self.dropbox_client_secret)
