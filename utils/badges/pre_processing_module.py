from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import pandas as pd
import logging
from dataclasses import dataclass
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

@dataclass
class PreprocessingConfig:
    """Configuration for preprocessing."""
    main_event: str  # The main event name (e.g., "Convention 2025 - San Francisco")
    sub_event: Optional[str] = None  # Optional sub-event to filter by
    timezone: str = "America/Los_Angeles"  # Default timezone for timestamps
    inclusion_list: Optional[List[str]] = None  # Optional list of Contact IDs to include
    created_on_filter: Optional[str] = None  # Optional "on or after" date filter (format: "6/11/2025" or "6/11/2025 2:56:51 PM")
    
    def __post_init__(self):
        self.tz = pytz.timezone(self.timezone)
        self.event_guest_view_id = "c582e1a8-43d5-ef11-8eea-000d3a351566"  # Event Guests
        self.qr_codes_view_id = "64368653-6f63-49c9-9365-0c69fcd938c1"      # QR Codes
        self.table_reservations_view_id = "fa417cde-f4d4-ef11-8eea-000d3a351566"  # Table Reservations
        self.form_responses_view_id = "f8645669-fa43-f011-877a-000d3a35dcd3"  # Form Responses
        
        # Entity names for each view
        self.event_guest_entity = "crca7_eventguest"
        self.qr_codes_entity = "aha_eventguestqrcodes"
        self.table_reservations_entity = "aha_tablereservation"
        self.form_responses_entity = "aha_eventformresponses"
        
        # Validate inclusion list if provided
        if self.inclusion_list is not None:
            # Ensure all IDs are strings and strip whitespace
            self.inclusion_list = [str(id).strip() for id in self.inclusion_list if str(id).strip()]
            # Remove duplicates while preserving order
            self.inclusion_list = list(dict.fromkeys(self.inclusion_list))
        
        # Parse and validate created_on_filter if provided
        self.created_on_datetime = None
        if self.created_on_filter is not None:
            self.created_on_datetime = self._parse_created_on_filter(self.created_on_filter)
    
    def _parse_created_on_filter(self, date_str: str) -> Optional[datetime]:
        """Parse the created_on_filter string into a datetime object.
        
        Supports formats like:
        - "6/11/2025"
        - "6/11/2025 2:56:51 PM"
        - "12/31/2025 11:30:00 AM"
        """
        if not date_str or not date_str.strip():
            return None
            
        date_str = date_str.strip()
        
        # Try different date formats
        formats_to_try = [
            "%m/%d/%Y %I:%M:%S %p",  # "6/11/2025 2:56:51 PM"
            "%m/%d/%Y %I:%M %p",     # "6/11/2025 2:56 PM"
            "%m/%d/%Y",              # "6/11/2025"
            "%m-%d-%Y %I:%M:%S %p",  # "6-11-2025 2:56:51 PM"
            "%m-%d-%Y %I:%M %p",     # "6-11-2025 2:56 PM"
            "%m-%d-%Y",              # "6-11-2025"
        ]
        
        for date_format in formats_to_try:
            try:
                parsed_date = datetime.strptime(date_str, date_format)
                # If no time specified, set to beginning of day
                if date_format in ["%m/%d/%Y", "%m-%d-%Y"]:
                    parsed_date = parsed_date.replace(hour=0, minute=0, second=0, microsecond=0)
                
                # Localize to the configured timezone
                localized_date = self.tz.localize(parsed_date)
                logger.info(f"Successfully parsed date filter: '{date_str}' -> {localized_date}")
                return localized_date
                
            except ValueError:
                continue
        
        # If none of the formats worked, log a warning and return None
        logger.warning(f"Could not parse date filter: '{date_str}'. Expected formats: '6/11/2025' or '6/11/2025 2:56:51 PM'")
        return None
        
    def get_output_filename(self, prefix: str = "MAIL_MERGE") -> str:
        """Generate output filename based on configuration."""
        timestamp = datetime.now(self.tz).strftime('%Y%m%d_%H%M%S')
        if self.sub_event:
            # Clean sub-event name for filename
            clean_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in self.sub_event)
            return f"{prefix}_{clean_name}_{timestamp}.xlsx"
        return f"{prefix}_v3_{timestamp}.xlsx"

class PreprocessingBase(ABC):
    """Abstract base class for event preprocessing."""
    
    # Define core contact columns that should always be included
    CONTACT_COLUMNS = [
        'Contact ID', 
        'First Name', 
        'Last Name', 
        'Title', 
        'Local Club', 
        'Gender', 
        'Age',
        'Cell Phone',
        'QR Code'
    ]
    
    NAME_COLUMNS = {
        'First Name (Existing Contact) (Contact)': 'First Name',
        'Last Name (Existing Contact) (Contact)': 'Last Name',
        'Cell Phone (Existing Contact) (Contact)': 'Cell Phone'
    }
    
    @abstractmethod
    def get_value_mappings(self) -> Dict[str, str]:
        """Return a dictionary mapping old values to new values for preprocessing."""
        pass
    
    @abstractmethod
    def get_contains_mappings(self) -> Dict[str, str]:
        """Return a dictionary for partial text matching and removal."""
        pass

    def _format_name(self, name: Any) -> str:
        """Format a name to have proper title case.
        
        Examples:
            "JOHN DOE" -> "John Doe"
            "john doe" -> "John Doe"
            "John-Doe" -> "John-Doe"
            "MARY JANE-DOE" -> "Mary Jane-Doe"
        """
        if pd.isna(name):
            return name
            
        name = str(name).strip()
        
        # Handle hyphenated names separately
        if '-' in name:
            parts = name.split('-')
            return '-'.join(part.strip().title() for part in parts)
            
        # Handle regular names
        return name.strip().title()
    
    def preprocess_value(self, value: Any, column_name: Optional[str] = None) -> str:
        """Replace values according to the mapping dictionary."""
        if pd.isna(value):  # Handle NaN/None values
            return ''
            
        value = str(value).strip()  # Convert to string and strip whitespace

        # First try exact match
        value_mappings = self.get_value_mappings()
        if value in value_mappings:
            return value_mappings[value].strip()

        # Then try contains match
        contains_mappings = self.get_contains_mappings()
        for contains_text, replacement in contains_mappings.items():
            if contains_text in value:
                value = value.replace(contains_text, replacement).strip()
        
        return value

    def _get_relevant_columns(self, df: pd.DataFrame, sub_event: str) -> List[str]:
        """Get list of columns relevant for the sub-event."""
        # Start with core contact columns, excluding QR Code for sub-events
        relevant_cols = [col for col in self.CONTACT_COLUMNS if col != 'QR Code' and col in df.columns]
        
        # Add the sub-event column itself
        if sub_event in df.columns:
            relevant_cols.append(sub_event)
            
        # Add any related columns (e.g., table assignments, form responses)
        for col in df.columns:
            if col.startswith(f"{sub_event} ~"):
                relevant_cols.append(col)
                
        return relevant_cols

    def filter_by_sub_event(self, df: pd.DataFrame, sub_event: Optional[str] = None) -> pd.DataFrame:
        """Filter DataFrame rows and columns for the sub-event."""
        if not sub_event:
            return df
            
        # Get contacts registered for the sub-event
        # First check if the sub-event exists as a column
        if sub_event not in df.columns:
            logger.warning(f"Sub-event column '{sub_event}' not found in DataFrame")
            logger.info("Available columns:")
            for col in df.columns:
                logger.info(f"  - {col}")
            return pd.DataFrame(columns=df.columns)  # Return empty DataFrame with same structure
            
        # Keep contacts where the sub-event column is not null
        sub_event_contacts = df[df[sub_event].notna()]['Contact ID'].unique()
        if len(sub_event_contacts) == 0:
            logger.warning(f"No contacts found for sub-event: {sub_event}")
            return pd.DataFrame(columns=df.columns)  # Return empty DataFrame with same structure
            
        filtered_df = df[df['Contact ID'].isin(sub_event_contacts)].copy()
        
        # Get only relevant columns
        relevant_cols = self._get_relevant_columns(filtered_df, sub_event)
        filtered_df = filtered_df[relevant_cols]
        
        # Log what we're keeping
        logger.info(f"\nKeeping {len(filtered_df)} contacts and {len(relevant_cols)} columns for {sub_event}")
        logger.info("Columns kept:")
        for col in relevant_cols:
            logger.info(f"  - {col}")
            
        return filtered_df

    def preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Preprocess all string columns in the dataframe."""
        df = df.copy()  # Create a copy to avoid modifying the original
        
        # First handle name formatting and column renaming
        for old_col, new_col in self.NAME_COLUMNS.items():
            if old_col in df.columns:
                logger.info(f"Formatting and renaming {old_col} to {new_col}...")
                # Format the names
                df[old_col] = df[old_col].apply(self._format_name)
                # Rename the column
                df = df.rename(columns={old_col: new_col})
        
        # Apply preprocessing to all other string columns
        logger.info("Preprocessing remaining data values...")
        for column in df.select_dtypes(include=['object']).columns:
            if column not in self.NAME_COLUMNS.values():  # Skip name columns as they're already processed
                df.loc[0:, column] = df.loc[0:, column].apply(lambda x: self.preprocess_value(x, column))
        
        # Sub-event filtering is now handled at the main level before preprocessing
        # Just ensure we have all required columns that exist in the dataframe
        logger.info("Processing with all available columns")
        available_columns = [col for col in self.CONTACT_COLUMNS if col in df.columns]
        other_columns = [col for col in df.columns if col not in self.CONTACT_COLUMNS]
        df = df[available_columns + other_columns]
        
        return df 