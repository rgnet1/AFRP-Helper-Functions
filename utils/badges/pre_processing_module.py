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
    
    def __post_init__(self):
        self.tz = pytz.timezone(self.timezone)
        
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
        'QR Code'
    ]
    
    NAME_COLUMNS = {
        'First Name (Existing Contact) (Contact)': 'First Name',
        'Last Name (Existing Contact) (Contact)': 'Last Name'
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
        # Keep contacts where the sub-event column contains the sub-event name
        sub_event_contacts = df[df[sub_event].notna() & (df[sub_event].str.contains(sub_event, na=False))]['Contact ID'].unique()
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
        
        # Check if we need to process a sub-event
        has_config = hasattr(self, 'config') and self.config is not None
        has_sub_event = has_config and hasattr(self.config, 'sub_event') and self.config.sub_event is not None
        
        if has_sub_event:
            logger.info(f"Processing sub-event {self.config.sub_event} - excluding QR Code")
            df = self.filter_by_sub_event(df, self.config.sub_event)
        else:
            logger.info("Processing entire event with all columns")
            # For main event, ensure we have all required columns that exist in the dataframe
            available_columns = [col for col in self.CONTACT_COLUMNS if col in df.columns]
            other_columns = [col for col in df.columns if col not in self.CONTACT_COLUMNS]
            df = df[available_columns + other_columns]
        
        return df 