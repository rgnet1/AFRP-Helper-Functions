"""
Event preprocessing package for different events.
Automatically discovers and registers all preprocessing classes.
"""
import os
import re
import importlib
import inspect
import logging
from typing import Dict, Type
from utils.badges.pre_processing_module import PreprocessingBase

logger = logging.getLogger(__name__)

def discover_preprocessors() -> Dict[str, Type]:
    """
    Dynamically discover all preprocessor classes in this directory.
    Returns a dictionary mapping display names to preprocessor classes.
    """
    preprocessors = {}
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Scan all .py files in the directory
    for filename in os.listdir(current_dir):
        if filename.endswith('.py') and filename not in ['__init__.py']:
            module_name = filename[:-3]  # Remove .py extension
            
            try:
                # Import the module
                module = importlib.import_module(f'utils.badges.event_preprocessing.{module_name}')
                
                # Find all classes that inherit from PreprocessingBase
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, PreprocessingBase) and obj != PreprocessingBase:
                        # Convert class name to display name
                        # e.g., "Convention2025Preprocessing" -> "Convention 2025"
                        display_name = name.replace('Preprocessing', '').strip()
                        # Add spaces before capitals (Convention2025 -> Convention 2025)
                        display_name = re.sub(r'(\w)([A-Z])', r'\1 \2', display_name)
                        
                        preprocessors[display_name] = obj
                        logger.info(f"Registered preprocessor: {display_name} from {module_name}.py")
            
            except Exception as e:
                logger.warning(f"Failed to load preprocessor from {filename}: {e}")
    
    return preprocessors

# Automatically discover and export all preprocessors
preprocessing_implementations = discover_preprocessors()
