import os
import re
from datetime import datetime
from typing import Dict, Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)

class FileTypes:
    """Constants for file types."""
    REGISTRATION = "Registration List"
    SEATING = "Seating Chart"
    QR_CODES = "QR Codes"
    FORM_RESPONSES = "Form Responses"

class FileValidator:
    """Handles file validation and type detection for convention badge processing."""

    @staticmethod
    def is_valid_excel(filename: str) -> bool:
        """Check if file has a valid Excel extension."""
        return filename.lower().endswith('.xlsx') and not filename.lower().endswith('.xlsxzone.identifier')

    @staticmethod
    def get_file_type(filename: str) -> Optional[str]:
        """
        Determine the type of file based on its name.
        
        Args:
            filename: Name of the file to check
            
        Returns:
            One of the FileTypes constants or None if type cannot be determined
        """
        filename = filename.lower()
        logger.debug(f"Checking file type for: {filename}")
        
        # Define patterns for each file type with more variations
        patterns = {
            FileTypes.REGISTRATION: [
                'registration list',
                'registration_list',
                'registration-list',
                'registrationlist',
                'registration',
                'reg list',
                'reg_list',
                'reglist'
            ],
            FileTypes.SEATING: [
                'seating chart',
                'seating_chart',
                'seating-chart',
                'seatingchart',
                'seating',
                'seat chart',
                'seat_chart'
            ],
            FileTypes.QR_CODES: [
                'qr codes',
                'qr_codes',
                'qr-codes',
                'qrcodes',
                'qr code',
                'qr_code',
                'qr'
            ],
            FileTypes.FORM_RESPONSES: [
                'form responses',
                'form_responses',
                'form-responses',
                'formresponses',
                'from responses',  # Common typo
                'from_responses',
                'fromresponses',
                'form response',
                'from response',
                'from'
            ]
        }
        
        # Replace all separators with spaces for consistent matching
        test_name = re.sub(r'[_\-]', ' ', filename)
        logger.debug(f"Normalized filename for matching: {test_name}")
        
        # Check each file type's patterns
        for file_type, type_patterns in patterns.items():
            # Normalize patterns too
            normalized_patterns = [re.sub(r'[_\-]', ' ', pattern) for pattern in type_patterns]
            for pattern in normalized_patterns:
                if pattern in test_name:
                    logger.debug(f"Matched file type {file_type} with pattern '{pattern}'")
                    return file_type
        
        logger.debug("No file type pattern matched")
        logger.debug("Available patterns:")
        for file_type, type_patterns in patterns.items():
            logger.debug(f"  {file_type}:")
            for pattern in type_patterns:
                logger.debug(f"    - {pattern}")
        
        return None

    @staticmethod
    def parse_filename_datetime(filename: str) -> Optional[Tuple[str, datetime]]:
        """
        Parse filename to extract type and datetime information.
        
        Args:
            filename: Name of the file to parse
            
        Returns:
            Tuple of (file_type, datetime) or None if parsing fails
        """
        name = os.path.splitext(filename)[0]
        logger.debug(f"Parsing datetime from filename: {name}")
        
        # More flexible datetime pattern that matches your file format
        datetime_pattern = r'(\d{1,2}-\d{1,2}-\d{4}[_ ]?\d{1,2}-\d{1,2}-\d{2}[_ ]?(?:AM|PM))'
        
        # First determine the file type
        file_type = FileValidator.get_file_type(filename)
        if not file_type:
            logger.debug("Could not determine file type")
            return None
        
        # Then try to find the datetime
        match = re.search(datetime_pattern, name, re.IGNORECASE)
        if match:
            datetime_str = match.group(1)
            try:
                # Handle both underscore and space separators
                datetime_str = datetime_str.replace('_', ' ')
                dt = datetime.strptime(datetime_str, '%m-%d-%Y %I-%M-%S %p')
                logger.debug(f"Successfully parsed datetime: {dt}")
                return file_type, dt
            except ValueError as e:
                logger.debug(f"Failed to parse datetime: {e}")
        
        logger.debug("No datetime pattern matched")
        return None

    @staticmethod
    def find_latest_files(directory: str = '.') -> Dict[str, str]:
        """
        Find the latest version of each file type in the directory.
        
        Args:
            directory: Directory to search in (defaults to current directory)
            
        Returns:
            Dictionary mapping file types to their latest filenames
            
        Raises:
            ValueError: If any required file type is missing
        """
        logger.debug(f"Searching for files in directory: {directory}")
        files = [f for f in os.listdir(directory) if FileValidator.is_valid_excel(f)]
        logger.debug(f"Found Excel files: {files}")
        
        latest_files = {
            FileTypes.REGISTRATION: None,
            FileTypes.SEATING: None,
            FileTypes.QR_CODES: None,
            FileTypes.FORM_RESPONSES: None
        }
        
        latest_timestamps = {
            FileTypes.REGISTRATION: datetime.min,
            FileTypes.SEATING: datetime.min,
            FileTypes.QR_CODES: datetime.min,
            FileTypes.FORM_RESPONSES: datetime.min
        }
        
        for file in files:
            file_type = FileValidator.get_file_type(file)
            if file_type:
                parsed = FileValidator.parse_filename_datetime(file)
                if parsed:
                    _, file_datetime = parsed
                else:
                    # If we can't parse the datetime, use file modification time
                    file_datetime = datetime.fromtimestamp(os.path.getmtime(os.path.join(directory, file)))
                
                if file_datetime > latest_timestamps[file_type]:
                    latest_files[file_type] = file
                    latest_timestamps[file_type] = file_datetime
                    logger.debug(f"Updated latest {file_type} file to: {file}")
        
        # Verify we have all required files
        missing_files = [ft for ft, f in latest_files.items() if f is None]
        if missing_files:
            logger.error(f"Missing required files: {missing_files}")
            raise ValueError(f"Missing required files: {', '.join(missing_files)}")
        
        logger.debug("Latest files found:")
        for file_type, filename in latest_files.items():
            logger.debug(f"  {file_type}: {filename}")
            
        return latest_files

    @staticmethod
    def get_required_file_types() -> List[str]:
        """Get list of all required file types."""
        return [
            FileTypes.REGISTRATION,
            FileTypes.SEATING,
            FileTypes.QR_CODES,
            FileTypes.FORM_RESPONSES
        ] 