import logging
from typing import Dict, Optional
import pandas as pd
from utils.badges.pre_processing_module import PreprocessingBase, PreprocessingConfig

logger = logging.getLogger(__name__)

class Lex2026Preprocessing(PreprocessingBase):
    """Preprocessing implementation for Lexington 2026 Mid-Year Meeting."""
    
    def __init__(self, config: Optional[PreprocessingConfig] = None):
        """Initialize with optional configuration."""
        self.config = config
    
    def get_value_mappings(self) -> Dict[str, str]:
        """Return value mappings specific to Lexington 2026."""
        return {
            # Meal preferences
            "Steak": "S",
            "Fish": "F",
            "Vegetarian": "V",
            "Chicken": "C",
            "Vegan": "VG",
            
            # Club affiliations
            "No Club Affiliation": " ",
            "No Affiliation": " ",
            
            # Common event name shortenings
            "Mid-Year Meeting 2026 - Lexington": "Lexington 2026",
            "Mid-Year Meeting 2026": "Lexington 2026",
            
            # Add more event-specific mappings as needed
        }
    
    def get_contains_mappings(self) -> Dict[str, str]:
        """Return contains mappings specific to Lexington 2026."""
        return {
            # Clean up reservation notes
            "- Reserved": "",
            "- SPONSOR": "",
            "- AFRP Board Reserved": "",
            "- Will be removed after dinner": "",
            
            # Clean up club name prefixes
            "Ramallah Federation in ": "",
            "American Federation of Ramallah Palestine - ": "",
            "AFRP - ": "",
            
            # # Clean up event notes
            # "- (children must be supervised by parent)": "",
            # "- (children must be supervised by parent. $60 per child)": "",
            # "-  (children must be supervised by parent. $60 per child)": "",
            # "(Ages": "",
            # "(18+": "",
            # "(21+": "",
            
            # Add more event-specific string cleanups as needed
        }
    
    def preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Preprocess the DataFrame for Lexington 2026."""
        # Call parent class preprocessing first
        df = super().preprocess_dataframe(df)
        
        # Add any Lexington 2026-specific DataFrame transformations here
        # Example: Special column handling, data validation, etc.
        
        logger.info(f"Lex2026 preprocessing complete. Final shape: {df.shape}")
        return df
