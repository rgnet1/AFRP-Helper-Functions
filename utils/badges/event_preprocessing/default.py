import logging
from typing import Dict, Optional
import pandas as pd
from utils.badges.pre_processing_module import PreprocessingBase, PreprocessingConfig

logger = logging.getLogger(__name__)

class DefaultPreprocessing(PreprocessingBase):
    """Default preprocessing implementation with no custom mappings."""
    
    def __init__(self, config: Optional[PreprocessingConfig] = None):
        """Initialize with optional configuration."""
        self.config = config
    
    def get_value_mappings(self) -> Dict[str, str]:
        """Return empty value mappings (no custom transformations)."""
        return {}
    
    def get_contains_mappings(self) -> Dict[str, str]:
        """Return empty contains mappings (no text replacements)."""
        return {}
    
    def preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Preprocess the DataFrame with base functionality only."""
        return super().preprocess_dataframe(df)
