import os
import re
import logging
from typing import Optional, Tuple
from utils.magazine.config import MagazineConfig
from utils.magazine.dropbox_handler import DropboxHandler
from utils.magazine.server_handler import ServerHandler
from utils.magazine.send_text import SMSSender

class MagazineProcessor:
    """Main class for handling magazine processing workflow."""
    
    def __init__(self, config: MagazineConfig):
        """Initialize MagazineProcessor with configuration.
        
        Args:
            config: MagazineConfig instance containing necessary settings
        """
        self.config = config
        self.dropbox = DropboxHandler(config)
        self.notifier = SMSSender(config.email, config.email_password)

    def convert_filename(self, filename: str) -> Tuple[str, Optional[str]]:
        """Convert magazine filename to standard format.
        
        Args:
            filename: Original filename
            
        Returns:
            Tuple of (new filename, year) or (original filename, None) if no match
        """
        # Use regex to extract necessary information
        match = re.match(r'Vol(\d+)-No(\d+)_(\d+)-(\w+)-(\w+)_HathiheRamallah_web\.pdf', filename)
        
        if match:
            volume = match.group(1)
            number = match.group(2)
            year = match.group(3)
            month1 = match.group(4)
            month2 = match.group(5)
            
            # Convert to the desired format
            new_filename = f"Vol. {volume} No. {number} {month1}-{month2}, {year}.pdf"
            return new_filename, year
        else:
            logging.info(f"{filename} did not match format. Skipping")
            print(f"{filename} did not match format. Skipping")
            return filename, None

    def process_magazine_files(self) -> None:
        """Process magazine files from Dropbox and upload to server."""
        # First check for new files from Dropbox
        downloaded_file = self.dropbox.process_latest_file()
        if not downloaded_file:
            logging.info("No new files to process")
            return

        # List all PDF files in current directory
        pdf_files = [f for f in os.listdir() if f.endswith('.pdf') and f.startswith("Vol")]
        
        # Use context manager for server connection
        with ServerHandler(self.config) as server:
            for file in pdf_files:
                self._process_single_file(file, server)

    def _process_single_file(self, filename: str, server: ServerHandler) -> None:
        """Process a single magazine file.
        
        Args:
            filename: Name of file to process
            server: Connected ServerHandler instance
        """
        # Get the converted filename
        new_filename, year = self.convert_filename(filename)

        # Skip if filename didn't match pattern
        if new_filename == filename:
            return

        logging.info(f"Processing: {filename} -> {new_filename}")
        print(f"\n-------------------------------------------------")
        print(f"Re-name: {filename} -> {new_filename}")

        # Rename the file locally
        os.rename(filename, new_filename)

        # Construct remote path
        remote_path = f"{self.config.server_path}{year}/"

        # Verify local file exists after rename
        if not os.path.exists(new_filename):
            logging.error(f"Local file {new_filename} does not exist!")
            print(f"Local file {new_filename} does not exist!")
            return

        # Verify remote directory exists
        if not server.remote_path_exists(remote_path):
            logging.error(f"Remote path {remote_path} does not exist")
            print(f"Remote path {remote_path} does not exist. Please make sure directory exists!")
            return

        # Construct full remote path
        remote_file_path = remote_path + new_filename

        # Skip if file already exists on server
        if server.remote_file_exists(remote_file_path):
            logging.info(f"{new_filename} already exists on the server. Skipping!")
            print(f"{new_filename} already exists on the server. Skipping!")
            return

        # Upload file with progress bar
        def progress_callback(transferred: int, total: int) -> None:
            """Display upload progress."""
            bar_length = 50
            progress = transferred / total
            block = int(round(bar_length * progress))
            bar = "|" + "=" * block + "-" * (bar_length - block) + "|"
            print(f"\r{bar} {progress:.2%}", end='\r')
            if transferred == total:
                print()

        if server.upload_file(new_filename, remote_file_path, progress_callback):
            message = f"New Magazine: Successfully added: {new_filename} to server"
            logging.info(message)
            print(message)
            
            # Send notifications
            if self.config.notification_credentials_valid:
                for number in self.config.notification_numbers.values():
                    if number:  # Only send if number is provided
                        self.notifier.send_message(number, self.notifier.VERIZON, message)

def main():
    """Main entry point for magazine processing."""
    try:
        config = MagazineConfig()
        processor = MagazineProcessor(config)
        processor.process_magazine_files()
    except Exception as e:
        logging.error(f"Error in magazine processing: {e}")
        print(f"Error in magazine processing: {e}")

if __name__ == "__main__":
    main()
