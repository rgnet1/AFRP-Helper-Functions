import logging
from utils.magazine.config import MagazineConfig
from utils.magazine.magazine_processor import MagazineProcessor

def main():
    """Main entry point for magazine download and processing."""
    try:
        # Set up logging
        logging.basicConfig(
            filename='dropbox_folder_download.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Initialize configuration
        config = MagazineConfig()
        
        # Create and run processor
        processor = MagazineProcessor(config)
        processor.process_magazine_files()
        
    except Exception as e:
        logging.error(f"Error in main process: {e}")
        print(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    main()
