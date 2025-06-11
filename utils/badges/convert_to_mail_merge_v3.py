import os
import sys
import pandas as pd
import warnings
import re
from datetime import datetime
import pytz
import logging
from typing import Dict, List, Tuple, Optional, Type
from utils.badges.event_statistics import EventStatisticsReport
from utils.badges.event_preprocessing.convention2025 import Convention2025Preprocessing
from utils.badges.pre_processing_module import PreprocessingConfig, PreprocessingBase
from utils.badges.file_validator import FileValidator, FileTypes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress openpyxl UserWarning about default style
warnings.simplefilter("ignore", UserWarning)

class RegistrationColumns:
    CONTACT_ID = "Contact ID (Existing Contact) (Contact)"
    FIRST_NAME = "First Name (Existing Contact) (Contact)"
    LAST_NAME = "Last Name (Existing Contact) (Contact)"
    TITLE = "Title (Existing Contact) (Contact)"
    LOCAL_CLUB = "Local Club (Existing Contact) (Contact)"
    GENDER = "Gender (Existing Contact) (Contact)"
    AGE = "Age (Existing Contact) (Contact)"
    EVENT = "Event"
    STATUS = "Status Reason"
    
    # Map of standardized names to possible column names in file
    MAPPINGS = {
        'Contact ID': [CONTACT_ID, 'Contact ID', 'Contact'],
        'First Name': [FIRST_NAME],
        'Last Name': [LAST_NAME],
        'Title': [TITLE],
        'Local Club': [LOCAL_CLUB],
        'Gender': [GENDER],
        'Age': [AGE],
        'Event': [EVENT, 'Event '],  # Note the space variant
        'Status': [STATUS]
    }

class SeatingColumns:
    CONTACT_ID = "Contact ID (Contact) (Contact)"
    EVENT = "Event"  # Use the Event column from seating chart
    TABLE = "Table"
    
    # Map of standardized names to possible column names in file
    MAPPINGS = {
        'Contact ID': [CONTACT_ID, 'Contact ID', 'Contact'],
        'Event': [EVENT],  # Only use Event column
        'Table': [TABLE]
    }

class QRCodeColumns:
    CONTACT_ID = "Contact ID (Event Guest Contact Id) (Contact)"
    QR_CODE = "QR Code Value"
    
    # Map of standardized names to possible column names in file
    MAPPINGS = {
        'Contact ID': [CONTACT_ID, 'Contact ID', 'Contact', 'Event Guest Contact Id'],
        'QR Code': [QR_CODE, 'QR Code', 'QR Code Value']
    }

class FormResponseColumns:
    CONTACT_ID = "Contact ID (Contact) (Contact)"
    EVENT = "Campaign"  # Use Campaign column from form responses
    QUESTION = "Form Question"
    RESPONSE = "Guest Response"
    
    # Map of standardized names to possible column names in file
    MAPPINGS = {
        'Contact ID': [CONTACT_ID, 'Contact ID', 'Contact'],
        'Event': [EVENT],  # Only use Campaign column
        'Question': [QUESTION, 'Form Question', 'Question'],
        'Response': [RESPONSE, 'Guest Response', 'Response', 'Answer']
    }

class EventRegistrationProcessorV3:
    def __init__(self, config: Optional[PreprocessingConfig] = None, preprocessor_class: Optional[Type[PreprocessingBase]] = None):
        """
        Initialize the processor with optional configuration and preprocessor class.
        
        Args:
            config: Optional configuration for preprocessing
            preprocessor_class: Optional class to use for preprocessing. If not provided, defaults to Convention2025Preprocessing
        """
        self.config = config
        if preprocessor_class is None:
            logger.debug("No preprocessor class provided, defaulting to Convention2025Preprocessing")
            preprocessor_class = Convention2025Preprocessing
        
        logger.debug(f"Initializing preprocessor with class: {preprocessor_class.__name__}")
        self.preprocessor = preprocessor_class(config)
        self.stats_reporter = EventStatisticsReport()
        
    def find_latest_files(self) -> Dict[str, str]:
        """Find the latest version of each file type in the directory."""
        return FileValidator.find_latest_files()

    def _find_column_name(self, df: pd.DataFrame, column_mappings: Dict[str, List[str]], required_column: str) -> Optional[str]:
        """Find the actual column name in the DataFrame based on possible mappings."""
        possible_names = column_mappings[required_column]
        for name in possible_names:
            if name in df.columns:
                return name
        return None

    def _standardize_columns(self, df: pd.DataFrame, column_mappings: Dict[str, List[str]]) -> Tuple[pd.DataFrame, List[str]]:
        """Standardize column names based on mappings and return missing columns."""
        # Clean column names
        df.columns = df.columns.str.strip()
        
        # Create reverse mapping
        column_mapping = {}
        missing_columns = []
        
        for standard_name, possible_names in column_mappings.items():
            found_name = self._find_column_name(df, column_mappings, standard_name)
            if found_name:
                column_mapping[found_name] = standard_name
            else:
                missing_columns.append(standard_name)
        
        # Rename columns to standard names
        if column_mapping:
            df = df.rename(columns=column_mapping)
            
        return df, missing_columns

    def process_registration_data(self, reg_df: pd.DataFrame) -> pd.DataFrame:
        """Process the main registration data."""
        logger.info("Registration file columns:")
        logger.info(reg_df.columns.tolist())
        
        # Standardize column names
        reg_df, missing_columns = self._standardize_columns(reg_df, RegistrationColumns.MAPPINGS)
        if missing_columns:
            logger.info("\nAvailable columns:")
            logger.info(reg_df.columns.tolist())
            raise ValueError(f"Missing required columns in registration data: {', '.join(missing_columns)}")
        
        # Filter for paid registrations
        paid_df = reg_df[reg_df['Status'] == 'Paid']
        logger.info(f"\nFound {len(paid_df)} paid registrations out of {len(reg_df)} total")
        
        # Get unique events
        unique_events = paid_df['Event'].unique()
        logger.info(f"\nFound {len(unique_events)} unique events:")
        for event in unique_events:
            logger.info(f"  - {event}")
        
        # Create base DataFrame with unique contacts using only the key identifying columns
        unique_columns = ['Contact ID', 'First Name', 'Last Name', 'Title', 'Local Club', 'Gender', 'Age']
        transformed_df = paid_df[unique_columns].drop_duplicates(subset=['Contact ID']).reset_index(drop=True)
        
        logger.info(f"\nFound {len(transformed_df)} unique contacts")

        # Format names to proper case
        logger.info("Formatting names to proper case...")
        transformed_df['First Name'] = transformed_df['First Name'].apply(lambda x: str(x).strip().title() if pd.notna(x) else x)
        transformed_df['Last Name'] = transformed_df['Last Name'].apply(lambda x: str(x).strip().title() if pd.notna(x) else x)
        
        # Add each event as a new column
        for event in unique_events:
            transformed_df[event] = transformed_df.apply(
                lambda row: event if event in paid_df[
                    paid_df['Contact ID'] == row['Contact ID']
                ]['Event'].values else None,
                axis=1
            )
        
        return transformed_df

    def add_seating_info(self, df: pd.DataFrame, seating_df: pd.DataFrame) -> pd.DataFrame:
        """Add seating information for each event."""
        logger.debug("Seating file columns:")
        logger.debug(seating_df.columns.tolist())
        
        # Clean column names
        seating_df.columns = seating_df.columns.str.strip()
        
        # Standardize column names
        seating_df, missing_columns = self._standardize_columns(seating_df, SeatingColumns.MAPPINGS)
        if missing_columns:
            logger.debug("Available columns:")
            logger.debug(seating_df.columns.tolist())
            raise ValueError(f"Missing required columns in seating data: {', '.join(missing_columns)}")
        
        # Group seating by Contact ID and Event, handling duplicates
        logger.info("Processing seating assignments...")
        seating_info = seating_df.sort_values('Created On', ascending=False).drop_duplicates(['Contact ID', 'Event'])
        
        logger.debug(f"Found {len(seating_info)} unique seating assignments")
        
        # Get unique events and initialize table columns with empty strings
        events_with_seating = sorted(seating_df['Event'].unique())
        logger.info("Initializing table columns...")
        for event in events_with_seating:
            column_name = f"{event} ~ Table"
            df[column_name] = ''
            
        # Assign actual table values, skipping blanks/NaNs
        logger.info("Assigning tables to contacts...")
        for _, row in seating_info.iterrows():
            table_value = str(row['Table']).strip() if pd.notna(row['Table']) else ''
            if table_value:
                column_name = f"{row['Event']} ~ Table"
                df.loc[df['Contact ID'] == row['Contact ID'], column_name] = table_value

        # Print unique events from seating chart for verification
        logger.info("Events found in seating chart:")
        for event in events_with_seating:
            logger.info(f"  - {event}")
        
        # Print summary of table assignments
        logger.info("Table assignment summary:")
        for event in events_with_seating:
            column_name = f"{event} ~ Table"
            # Count non-empty strings for assignments
            assigned = df[df[column_name] != ''].shape[0]
            logger.info(f"  - {event}: {assigned} assignments")
        
        return df

    def add_form_responses(self, df: pd.DataFrame, forms_df: pd.DataFrame) -> pd.DataFrame:
        """Add form responses for each event."""
        logger.debug("Form responses file columns:")
        logger.debug(forms_df.columns.tolist())
        
        # Standardize column names
        forms_df, missing_columns = self._standardize_columns(forms_df, FormResponseColumns.MAPPINGS)
        if missing_columns:
            logger.debug("Available columns:")
            logger.debug(forms_df.columns.tolist())
            raise ValueError(f"Missing required columns in form responses data: {', '.join(missing_columns)}")
        
        # Ensure Created On is properly parsed as datetime
        try:
            forms_df['Created On'] = pd.to_datetime(forms_df['Created On'])
        except Exception as e:
            logger.warning(f"Could not parse Created On column: {str(e)}")
            # If we can't parse Created On, we'll just use the first response for each contact
            forms_df['Created On'] = pd.Timestamp.now()
        
        # Get unique questions per event
        event_questions = forms_df.groupby('Event')['Question'].unique()
        logger.info("Found form questions by event:")
        for event in event_questions.index:
            logger.info(f"\n{event}:")
            for question in event_questions[event]:
                logger.info(f"  - {question}")
        
        # For each event and question, create a column and populate responses
        for event in event_questions.index:
            for question in event_questions[event]:
                column_name = f"{event} ~ {question}"
                
                # Get responses for this event and question
                event_question_responses = forms_df[
                    (forms_df['Event'] == event) & 
                    (forms_df['Question'] == question)
                ].copy()
                
                # Check for duplicates
                duplicates = event_question_responses.groupby('Contact ID').size()
                if (duplicates > 1).any():
                    logger.warning(f"Found duplicate responses for {event} - {question}:")
                    for contact_id in duplicates[duplicates > 1].index:
                        dupes = event_question_responses[event_question_responses['Contact ID'] == contact_id]
                        logger.warning(f"Contact ID: {contact_id}")
                        for _, dupe in dupes.iterrows():
                            logger.warning(f"  Response: {dupe['Response']}")
                            logger.warning(f"  Created On: {dupe['Created On']}")
                
                # Keep only the most recent response for each contact
                latest_responses = (event_question_responses
                                  .sort_values('Created On', ascending=False)
                                  .groupby('Contact ID', as_index=False)
                                  .first())
                
                # Create a dictionary mapping Contact ID to Response instead of using Series
                response_dict = dict(zip(latest_responses['Contact ID'], latest_responses['Response']))
                
                # Add responses to main DataFrame using the dictionary
                df[column_name] = df['Contact ID'].map(response_dict)
        
        return df

    def add_qr_codes(self, df: pd.DataFrame, qr_df: pd.DataFrame) -> pd.DataFrame:
        """Add QR code information."""
        logger.debug("QR codes file columns:")
        logger.debug(qr_df.columns.tolist())
        
        # Standardize column names
        qr_df, missing_columns = self._standardize_columns(qr_df, QRCodeColumns.MAPPINGS)
        if missing_columns:
            logger.debug("Available columns:")
            logger.debug(qr_df.columns.tolist())
            raise ValueError(f"Missing required columns in QR codes data: {', '.join(missing_columns)}")
        
        # Ensure Created On is properly parsed as datetime
        try:
            qr_df['Created On'] = pd.to_datetime(qr_df['(Do Not Modify) Modified On'])
        except Exception as e:
            logger.warning(f"Could not parse Created On column: {str(e)}")
            # If we can't parse Created On, we'll just use the first QR code for each contact
            qr_df['Created On'] = pd.Timestamp.now()
        
        # Check for duplicates
        duplicates = qr_df.groupby('Contact ID').size()
        if (duplicates > 1).any():
            logger.warning("\nFound duplicate QR codes:")
            for contact_id in duplicates[duplicates > 1].index:
                dupes = qr_df[qr_df['Contact ID'] == contact_id]
                logger.warning(f"\nContact ID: {contact_id}")
                for _, dupe in dupes.iterrows():
                    logger.warning(f"  QR Code: {dupe['QR Code']}")
                    logger.warning(f"  Created On: {dupe['Created On']}")
                    logger.warning(f"  Contact Name: {dupe.get('First Name', '')} {dupe.get('Last Name', '')}")
        
        # Keep only the most recent QR code for each contact
        latest_qr_codes = (qr_df
                          .sort_values('Created On', ascending=False)
                          .groupby('Contact ID', as_index=False)
                          .first())
        
        # Create a dictionary mapping Contact ID to QR Code instead of using Series
        qr_code_dict = dict(zip(latest_qr_codes['Contact ID'], latest_qr_codes['QR Code']))
        
        # Map QR codes to Contact IDs using the dictionary
        df['QR Code'] = df['Contact ID'].map(qr_code_dict)
        logger.info(f"Added QR codes for {len(qr_code_dict)} contacts")
        return df

    def transform_and_merge(self) -> pd.DataFrame:
        """Main function to transform and merge all data sources."""
        try:
            # Find latest files
            files = self.find_latest_files()
            
            # Load all data sources
            reg_df = pd.read_excel(files[FileTypes.REGISTRATION])
            seating_df = pd.read_excel(files[FileTypes.SEATING])
            qr_df = pd.read_excel(files[FileTypes.QR_CODES])
            forms_df = pd.read_excel(files[FileTypes.FORM_RESPONSES])
            
            # Process main registration data
            result_df = self.process_registration_data(reg_df)
            
            # Add information from other sources
            result_df = self.add_seating_info(result_df, seating_df)
            result_df = self.add_form_responses(result_df, forms_df)
            result_df = self.add_qr_codes(result_df, qr_df)
            
            # Sort by last name, first name and reset index
            result_df = result_df.sort_values(
                by=['Last Name', 'First Name']
            ).reset_index(drop=True)
            
            # Apply preprocessing to all data rows
            logger.info("Preprocessing data values...")
            result_df = self.preprocessor.preprocess_dataframe(result_df)
            
            # Filter by sub-event if configured
            has_config = hasattr(self, 'config') and self.config is not None
            has_sub_event = has_config and hasattr(self.config, 'sub_event') and self.config.sub_event is not None
            
            if has_sub_event:
                logger.info(f"Filtering data for sub-event: {self.config.sub_event}")
                result_df = self.preprocessor.filter_by_sub_event(result_df, self.config.sub_event)
                logger.info(f"Found {len(result_df)} contacts for {self.config.sub_event}")
            else:
                logger.info("Processing entire event (no sub-event specified)")
            
            # Collect and generate statistics
            self.stats_reporter.collect_statistics(result_df)
            self.stats_reporter.generate_report()
            
            return result_df
            
        except Exception as e:
            logger.error(f"Error during processing: {str(e)}")
            raise

    def save_output(self, df: pd.DataFrame) -> None:
        """Save the merged data to an Excel file with appropriate name."""
        output_filename = (self.config.get_output_filename() if self.config 
                         else f'MAIL_MERGE_v3_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
        
        df.to_excel(output_filename, index=False)
        logger.info(f"Merged data saved to: {output_filename}")

def main(sub_event: Optional[str] = None):
    try:
        # Initialize processor
        processor = EventRegistrationProcessorV3()
        
        # Find latest files and load registration data to get main event
        files = processor.find_latest_files()
        reg_df = pd.read_excel(files[FileTypes.REGISTRATION])
        
        # Get main event (Convention 2025 - San Francisco)
        main_event = reg_df[reg_df['Status Reason'] == 'Paid']['Event '].iloc[0]
        
        # Initialize configuration if sub_event is specified
        config = PreprocessingConfig(
            main_event=main_event,
            sub_event=sub_event
        ) if sub_event else None
        
        # Reinitialize processor with configuration
        processor = EventRegistrationProcessorV3(config)
        
        # Process and merge all data
        merged_df = processor.transform_and_merge()
        
        # Save the output
        processor.save_output(merged_df)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.error("\nPlease ensure all required files are present in the current directory with the correct naming format:")
        logger.error("  - Registration List: *Registration List*.xlsx")
        logger.error("  - Seating Chart: *Seating Chart*.xlsx")
        logger.error("  - QR Codes: *QR Codes*.xlsx")
        logger.error("  - Form Responses: *(Form|From) Responses*.xlsx")

if __name__ == "__main__":
    main()