import logging
from utils.magazine.config import MagazineConfig
from utils.magazine.magazine_processor import MagazineProcessor

# Get logger for magazine download process
magazine_logger = logging.getLogger('MAGAZINE')
# No need to configure the logger here as it's already configured in scheduler.py

def main():
    """Main entry point for magazine download and processing."""
    try:
        # Initialize configuration
        config = MagazineConfig()
        magazine_logger.info("Starting magazine download process")
        
        # Create and run processor
        processor = MagazineProcessor(config)
        processor.process_magazine_files()
        
    except Exception as e:
        magazine_logger.error(f"Error in main process: {e}")
        raise

if __name__ == "__main__":
    main()
