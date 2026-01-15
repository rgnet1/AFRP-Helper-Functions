import logging
from typing import Dict, Optional
import pandas as pd
from utils.badges.pre_processing_module import PreprocessingBase, PreprocessingConfig

logger = logging.getLogger(__name__)

class Convention2025Preprocessing(PreprocessingBase):
    """Preprocessing implementation for Convention 2025."""
    
    def __init__(self, config: Optional[PreprocessingConfig] = None):
        """Initialize with optional configuration."""
        self.config = config
    
    def get_value_mappings(self) -> Dict[str, str]:
        """Return value mappings specific to Convention 2025."""
        return {
            "Steak": "S",
            "Level Up Party w/ DJ Habibeats (17+)": "Level Up",
            "Fish": "F",
            "Vegetarian": "V",
            "Madarae Night Club (21+)": "Madarae",
            "Young Adults Night at Nola (18+ Only)": "Nola",
            "Pizza Pool Day (Ages 13-17 only)": "Pool Day",
            "Hamooleh Family Feud": "Family Feud",
            "Top Golf (Ages 13 - 17)": "Top Golf",
            "Youth DJ Party  (Ages 13-17)": "DJ Party",
            "Ladies Trip to Santana Row": "Ladies Trip",
            "Discovery Bay Museum / Sausalito Trip": "Discovery Bay Museum",
            "Child: Chicken fingers & French fries": "CFF",
            "Child: Hamburger & French fries": "HFF",
            "Casino Night": "Casino Night",
            "No Club Affiliation": " ",
        }
    
    def get_contains_mappings(self) -> Dict[str, str]:
        """Return contains mappings specific to Convention 2025."""
        return {
            "- SF Reserved": "",
            "- SF reserved": "",
            "- SPONSOR": "",
            "- AFRP": "",
            "- Will be removed after dinner": "",
            "- Brezeit": "",
            "- SF/Brezeit": "",
            "- (children must be supervised by parent. $60 per child)": "",
            "-  (children must be supervised by parent. $60 per child)": "",
            "Ramallah Federation in ": "",
            "- (children must be supervised by parent)": "",
        }
    
    def preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Preprocess the DataFrame."""
        return super().preprocess_dataframe(df) 