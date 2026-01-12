import os
import json
import logging
import msal
import requests
import time
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from functools import wraps
import pandas as pd
from dotenv import load_dotenv

# Set up logging
logger = logging.getLogger(__name__)

# Cache decorator with TTL (Time To Live)
def cache_with_ttl(ttl_seconds=300):
    """
    Decorator to cache function results with a time-to-live.
    
    Args:
        ttl_seconds: Cache lifetime in seconds (default 5 minutes)
    """
    def decorator(func: Callable) -> Callable:
        cache = {}
        cache_times = {}
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = (func.__name__, str(args), str(sorted(kwargs.items())))
            current_time = time.time()
            
            # Check if cached result exists and is still valid
            if cache_key in cache and cache_key in cache_times:
                if current_time - cache_times[cache_key] < ttl_seconds:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return cache[cache_key]
                else:
                    logger.debug(f"Cache expired for {func.__name__}")
            
            # Call function and cache result
            logger.debug(f"Cache miss for {func.__name__}, fetching fresh data")
            result = func(*args, **kwargs)
            cache[cache_key] = result
            cache_times[cache_key] = current_time
            
            return result
        
        # Add method to clear cache
        def clear_cache():
            cache.clear()
            cache_times.clear()
            logger.info(f"Cache cleared for {func.__name__}")
        
        wrapper.clear_cache = clear_cache
        return wrapper
    
    return decorator

# Load .env from config directory
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
BASE_PATH = '/app' if IN_DOCKER else '.'
CONFIG_PATH = '/config' if IN_DOCKER else f"{BASE_PATH}/config"
load_dotenv(os.path.join(CONFIG_PATH, '.env'))

class DynamicsCRMClient:
    def __init__(self):
        self.tenant_id = os.getenv('DYNAMICS_TENANT_ID')
        self.client_id = os.getenv('DYNAMICS_CLIENT_ID')
        self.client_secret = os.getenv('DYNAMICS_CLIENT_SECRET')
        self.crm_url = os.getenv('DYNAMICS_CRM_URL')
        self.scope = [f"{self.crm_url}/.default"]
        
        if not all([self.tenant_id, self.client_id, self.client_secret, self.crm_url]):
            raise ValueError("Missing required environment variables for Dynamics CRM connection")
        
        self.access_token = self._get_access_token()

    def _get_access_token(self) -> str:
        """Get access token for Dynamics 365 CRM."""
        app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret
        )
        
        result = app.acquire_token_for_client(scopes=self.scope)
        
        if "access_token" not in result:
            raise Exception(f"Could not get access token: {result.get('error_description', '')}")
        
        return result["access_token"]

    def _make_request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
        """Make a request to Dynamics 365 CRM."""
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "OData-MaxVersion": "4.0",
            "OData-Version": "4.0",
            # Request formatted values for option sets, lookups, etc.
            "Prefer": 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
        }
        
        url = f"{self.crm_url}/api/data/v9.2/{endpoint}"
        
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=data
        )
        
        response.raise_for_status()
        return response.json()

    def get_event_guests(self, view_id: str) -> pd.DataFrame:
        """Fetch event guests data using a saved query/view."""
        # Expand to get related Contact entity data
        # Using $select to get specific fields and $expand to get related entities
        # Note: Navigation property names are case-sensitive!
        # Expand with all contact fields to ensure lookup fields (_aha_localclub2_value) are included
        # When you use $select in $expand, lookup fields may not be included automatically
        expand_query = "$expand=crca7_ExistingContact,crca7_Event($select=name)"
        endpoint = f"crca7_eventguests?{expand_query}"
        response = self._make_request(endpoint)
        df = self._process_response(response, "crca7_")
        
        # Flatten expanded entities
        df = self._flatten_expanded_columns(df)
        
        # Map API columns to Excel column names
        df = self._map_event_guest_columns(df)
        
        return df

    def get_qr_codes(self, view_id: str) -> pd.DataFrame:
        """Fetch QR codes data using a saved query/view."""
        # Expand to get Contact directly (not through Event Guest)
        expand_query = "$expand=aha_EventGuestContactId($select=contactid)"
        endpoint = f"aha_eventguestqrcodeses?{expand_query}"
        response = self._make_request(endpoint)
        df = self._process_response(response, "aha_")
        
        # Flatten and map columns
        df = self._flatten_qr_code_columns(df)
        df = self._map_qr_code_columns(df)
        
        return df

    def get_table_reservations(self, view_id: str) -> pd.DataFrame:
        """Fetch table reservations data using a saved query/view."""
        # NOTE: Using aha_tablereservations (seat assignments), not aha_seatingtables (physical tables)
        # Expand to get Contact, Event, and Table info
        expand_query = "$expand=aha_Contact($select=contactid),aha_Event($select=name),aha_Table($select=aha_name)"
        endpoint = f"aha_tablereservations?{expand_query}"
        response = self._make_request(endpoint)
        df = self._process_response(response, "aha_")
        
        # Flatten and map columns
        df = self._flatten_seating_columns(df)
        df = self._map_seating_columns(df)
        
        return df

    def get_form_responses(self, view_id: str) -> pd.DataFrame:
        """Fetch form responses data using a saved query/view."""
        # Expand to get Contact, Campaign (Event), and Form Question
        # Note: Navigation properties are case-sensitive! aha_Contact not aha_contact
        # Note: The question text is in aha_newcolumn field (not aha_name)
        expand_query = "$expand=aha_Contact($select=contactid),aha_Campaign($select=name),aha_FormQuestion($select=aha_newcolumn)"
        endpoint = f"aha_eventformresponseses?{expand_query}"
        response = self._make_request(endpoint)
        df = self._process_response(response, "aha_")
        
        # Flatten and map columns
        df = self._flatten_form_response_columns(df)
        df = self._map_form_response_columns(df)
        
        return df

    def _process_response(self, response: Dict, prefix: str) -> pd.DataFrame:
        """Process the API response into a DataFrame."""
        records = response.get("value", [])
        
        # Process each record to use formatted values where available
        processed_records = []
        for record in records:
            processed_record = {}
            formatted_suffix = "@OData.Community.Display.V1.FormattedValue"
            
            for key, value in record.items():
                # Skip the @odata annotations themselves
                if key.endswith(formatted_suffix):
                    continue
                
                # Check if there's a formatted value for this field
                formatted_key = f"{key}{formatted_suffix}"
                if formatted_key in record:
                    # Use the formatted value instead
                    processed_record[key] = record[formatted_key]
                else:
                    # Use the raw value
                    processed_record[key] = value
            
            processed_records.append(processed_record)
        
        df = pd.DataFrame(processed_records)
        
        # Clean up column names - remove prefix
        if not df.empty:
            df.columns = [col.replace(prefix, "") for col in df.columns]
        
        return df
    
    def _flatten_expanded_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flatten expanded entity columns from $expand queries."""
        if df.empty:
            return df
        
        formatted_suffix = "@OData.Community.Display.V1.FormattedValue"
        
        # Handle expanded 'crca7_ExistingContact' entity
        if 'ExistingContact' in df.columns:
            # Process each contact to use formatted values
            processed_contacts = []
            for contact in df['ExistingContact']:
                if contact is not None and isinstance(contact, dict):
                    processed_contact = {}
                    for key, value in contact.items():
                        # Skip formatted value annotations
                        if key.endswith(formatted_suffix):
                            continue
                        # Check if there's a formatted value for this field
                        formatted_key = f"{key}{formatted_suffix}"
                        if formatted_key in contact:
                            processed_contact[key] = contact[formatted_key]
                        else:
                            processed_contact[key] = value
                    processed_contacts.append(processed_contact)
                else:
                    processed_contacts.append({})
            
            contact_df = pd.DataFrame(processed_contacts)
            # Prefix with 'contact_' to avoid collisions
            contact_df.columns = ['contact_' + col for col in contact_df.columns]
            df = pd.concat([df.drop('ExistingContact', axis=1), contact_df], axis=1)
        
        # Handle expanded 'crca7_Event' entity (Campaign)
        if 'Event' in df.columns:
            event_df = pd.json_normalize(df['Event'])
            event_df.columns = ['event_' + col for col in event_df.columns]
            df = pd.concat([df.drop('Event', axis=1), event_df], axis=1)
        
        return df
    
    def _map_event_guest_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map Event Guest API columns to Excel export column names."""
        if df.empty:
            return df
        
        import logging
        logger = logging.getLogger(__name__)
        
        logger.debug(f"Event Guest columns BEFORE mapping: {df.columns.tolist()}")
        
        # Drop redundant top-level fields since we have expanded contact data
        # These would create duplicate columns after mapping
        redundant_cols = ['attendeefirstname', 'attendeelastname']
        df = df.drop(columns=[col for col in redundant_cols if col in df.columns], errors='ignore')
        
        # Mapping from API field names to Excel export column names
        # NOTE: Only map expanded entity fields, NOT lookup GUIDs to avoid duplicates
        column_mapping = {
            # Don't map eventguestid or _existingcontact_value - use expanded contact data
            'contact_contactid': 'Contact ID',
            'contact_aha_memberid': 'Member ID (Existing Contact) (Contact)',
            'contact_firstname': 'First Name (Existing Contact) (Contact)',
            'contact_lastname': 'Last Name (Existing Contact) (Contact)',
            'contact_salutation': 'Title (Existing Contact) (Contact)',  # Honorifics field (may be null)
            'contact_aha_title': 'Title (Existing Contact) (Contact)',  # Alternative title field
            'contact__aha_localclub2_value': 'Local Club (Existing Contact) (Contact)',  # Lookup field GUID
            'contact_aha_localclub2': 'Local Club (Existing Contact) (Contact)',  # Alternative mapping
            'contact_gendercode': 'Gender (Existing Contact) (Contact)',
            'contact_crca7_age': 'Age (Existing Contact) (Contact)',
            # Don't map _event_value - use expanded event name
            'event_name': 'Event',
            'statuscode': 'Status Reason',
            'createdon': 'Created On',
            'name': 'Name',
        }
        
        # Log what columns we have before mapping
        logger.info(f"Event Guest columns BEFORE mapping: {df.columns.tolist()}")
        
        # Rename columns that exist in the DataFrame
        rename_dict = {old: new for old, new in column_mapping.items() if old in df.columns}
        df = df.rename(columns=rename_dict)
        
        logger.info(f"Event Guest columns AFTER mapping: {df.columns.tolist()}")
        logger.info(f"Columns mapped: {list(rename_dict.keys())}")
        
        # Check for and handle any remaining duplicates
        if df.columns.duplicated().any():
            duplicates = df.columns[df.columns.duplicated()].unique().tolist()
            logger.warning(f"Found duplicate columns in Event Guest data: {duplicates}")
            # Keep first occurrence, drop duplicates
            df = df.loc[:, ~df.columns.duplicated()]
            logger.debug(f"Event Guest columns AFTER dedup: {df.columns.tolist()}")
        
        return df
    
    def _flatten_qr_code_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flatten QR Code expanded columns."""
        if df.empty:
            return df
        
        formatted_suffix = "@OData.Community.Display.V1.FormattedValue"
        
        def process_expanded_entity(entities, prefix):
            """Process expanded entities to use formatted values."""
            processed = []
            for entity in entities:
                if entity is not None and isinstance(entity, dict):
                    processed_entity = {}
                    for key, value in entity.items():
                        if key.endswith(formatted_suffix):
                            continue
                        formatted_key = f"{key}{formatted_suffix}"
                        if formatted_key in entity:
                            processed_entity[key] = entity[formatted_key]
                        else:
                            processed_entity[key] = value
                    processed.append(processed_entity)
                else:
                    processed.append({})
            result_df = pd.DataFrame(processed)
            result_df.columns = [prefix + col for col in result_df.columns]
            return result_df
        
        # Handle direct contact reference
        if 'EventGuestContactId' in df.columns:
            contact_df = process_expanded_entity(df['EventGuestContactId'], 'contact_')
            df = pd.concat([df.drop('EventGuestContactId', axis=1), contact_df], axis=1)
        
        return df
    
    def _map_qr_code_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map QR Code API columns to Excel export column names."""
        if df.empty:
            return df
        
        column_mapping = {
            'contact_contactid': 'Contact ID (Event Guest Contact Id) (Contact)',
            'qrcodevalue': 'QR Code Value',
            # Don't map 'qrcode' if 'qrcodevalue' exists to avoid duplicates
        }
        
        rename_dict = {old: new for old, new in column_mapping.items() if old in df.columns}
        df = df.rename(columns=rename_dict)
        
        # Handle duplicates
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]
        
        return df
    
    def _flatten_seating_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flatten Table Reservation expanded columns."""
        if df.empty:
            return df
        
        formatted_suffix = "@OData.Community.Display.V1.FormattedValue"
        
        def process_expanded_entity(entities, prefix):
            """Process expanded entities to use formatted values."""
            processed = []
            for entity in entities:
                if entity is not None and isinstance(entity, dict):
                    processed_entity = {}
                    for key, value in entity.items():
                        if key.endswith(formatted_suffix):
                            continue
                        formatted_key = f"{key}{formatted_suffix}"
                        if formatted_key in entity:
                            processed_entity[key] = entity[formatted_key]
                        else:
                            processed_entity[key] = value
                    processed.append(processed_entity)
                else:
                    processed.append({})
            result_df = pd.DataFrame(processed)
            result_df.columns = [prefix + col for col in result_df.columns]
            return result_df
        
        if 'Contact' in df.columns:
            contact_df = process_expanded_entity(df['Contact'], 'contact_')
            df = pd.concat([df.drop('Contact', axis=1), contact_df], axis=1)
        
        if 'Event' in df.columns:
            event_df = process_expanded_entity(df['Event'], 'event_')
            df = pd.concat([df.drop('Event', axis=1), event_df], axis=1)
        
        if 'Table' in df.columns:
            table_df = process_expanded_entity(df['Table'], 'table_')
            df = pd.concat([df.drop('Table', axis=1), table_df], axis=1)
        
        return df
    
    def _map_seating_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map Table Reservation API columns to Excel export column names."""
        if df.empty:
            return df
        
        # Only map expanded entity fields, not lookup GUIDs
        column_mapping = {
            'contact_contactid': 'Contact ID (Contact) (Contact)',
            # Don't map _contact_value - use expanded contact_contactid
            'event_name': 'Event',
            'table_aha_name': 'Table',
            # Fallback mappings if the above don't exist
            'table_name': 'Table',
            'name': 'Table',
            'createdon': 'Created On',
        }
        
        # Only use the first mapping that exists for each target
        rename_dict = {}
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in rename_dict.values():
                rename_dict[old_col] = new_col
        
        df = df.rename(columns=rename_dict)
        
        # Handle duplicates
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]
        
        # Clean up null/NaN Event values to prevent sorting errors
        # This MUST be done to avoid sorting errors with mixed types
        if 'Event' in df.columns:
            import numpy as np
            # First replace actual NaN with empty string, then convert everything to string
            df['Event'] = df['Event'].replace({np.nan: '', None: ''})
            df['Event'] = df['Event'].astype(str).replace('nan', '').replace('None', '')
        
        return df
    
    def _flatten_form_response_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flatten Form Response expanded columns."""
        if df.empty:
            return df
        
        formatted_suffix = "@OData.Community.Display.V1.FormattedValue"
        
        def process_expanded_entity(entities, prefix):
            """Process expanded entities to use formatted values."""
            processed = []
            for entity in entities:
                if entity is not None and isinstance(entity, dict):
                    processed_entity = {}
                    for key, value in entity.items():
                        if key.endswith(formatted_suffix):
                            continue
                        formatted_key = f"{key}{formatted_suffix}"
                        if formatted_key in entity:
                            processed_entity[key] = entity[formatted_key]
                        else:
                            processed_entity[key] = value
                    processed.append(processed_entity)
                else:
                    processed.append({})
            result_df = pd.DataFrame(processed)
            result_df.columns = [prefix + col for col in result_df.columns]
            return result_df
        
        # Note: Navigation properties are case-sensitive!
        if 'Contact' in df.columns:
            contact_df = process_expanded_entity(df['Contact'], 'contact_')
            df = pd.concat([df.drop('Contact', axis=1), contact_df], axis=1)
        
        if 'Campaign' in df.columns:
            campaign_df = process_expanded_entity(df['Campaign'], 'campaign_')
            df = pd.concat([df.drop('Campaign', axis=1), campaign_df], axis=1)
        
        if 'FormQuestion' in df.columns:
            question_df = process_expanded_entity(df['FormQuestion'], 'formquestion_')
            df = pd.concat([df.drop('FormQuestion', axis=1), question_df], axis=1)
        
        return df
    
    def _map_form_response_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map Form Response API columns to Excel export column names."""
        if df.empty:
            return df
        
        # Debug: Log what columns we have before mapping
        logger.debug(f"Form Response columns before mapping: {df.columns.tolist()}")
        
        # Only map expanded entity fields, not lookup GUIDs
        column_mapping = {
            'contact_contactid': 'Contact ID (Contact) (Contact)',
            # Don't map _contact_value - use expanded contact_contactid
            'campaign_name': 'Campaign',
            'formquestion_newcolumn': 'Form Question',  # Expanded from FormQuestion entity (aha_newcolumn field)
            'formquestion_aha_newcolumn': 'Form Question',  # Alternative field name
            'guestresponse': 'Guest Response',  # Top-level field
            'createdon': 'Created On',  # Add Created On for sorting/filtering
        }
        
        # Only use the first mapping that exists for each target
        rename_dict = {}
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns and new_col not in rename_dict.values():
                rename_dict[old_col] = new_col
        
        df = df.rename(columns=rename_dict)
        
        # Debug: Log what columns we have after mapping
        logger.debug(f"Form Response columns after mapping: {df.columns.tolist()}")
        
        # Handle duplicates
        if df.columns.duplicated().any():
            logger.warning(f"Found duplicate columns in Form Response data: {df.columns[df.columns.duplicated()].tolist()}")
            df = df.loc[:, ~df.columns.duplicated()]
        
        return df

    def download_data_by_type(self, data_type: str, view_id: str) -> pd.DataFrame:
        """Download data based on the type."""
        data_functions = {
            "event_guests": self.get_event_guests,
            "qr_codes": self.get_qr_codes,
            "table_reservations": self.get_table_reservations,
            "form_responses": self.get_form_responses
        }
        
        if data_type not in data_functions:
            raise ValueError(f"Unknown data type: {data_type}")
            
        return data_functions[data_type](view_id)

    def download_all_event_data(self, view_id: str) -> Dict[str, pd.DataFrame]:
        """
        Download all required data for badge generation.
        
        Args:
            view_id: The ID of the view containing event guests
            
        Returns:
            Dictionary containing DataFrames for different aspects of the event
        """
        try:
            # Get main event guests data
            guests_df = self.get_event_guests(view_id)
            
            # You can add more data fetching here as needed
            # For example:
            # sponsors_df = self.get_sponsors()
            # speakers_df = self.get_speakers()
            # etc.
            
            return {
                "event_guests": guests_df,
                # Add more dataframes as needed
            }
            
        except Exception as e:
            raise Exception(f"Error downloading event data: {str(e)}")
    
    # ========== Campaign/Event Management Methods ==========
    
    @cache_with_ttl(ttl_seconds=300)
    def get_open_campaigns(self) -> List[Dict[str, str]]:
        """
        Get list of main campaigns (campaigns without a parent) with 'Open' status.
        Cached for 5 minutes to reduce API calls.
        
        Also includes "Convention 2025 - San Francisco" for testing purposes.
        
        Returns:
            List of dictionaries with 'id' and 'name' keys
        """
        try:
            import urllib.parse
            
            # Query for campaigns with statuscode = 0 (Open) AND no parent campaign
            # _aha_parentcampaign_value eq null filters for main events only
            filter_clause = "statuscode eq 0 and _aha_parentcampaign_value eq null"
            endpoint = f"campaigns?$filter={urllib.parse.quote(filter_clause)}&$select=campaignid,name,_aha_parentcampaign_value&$orderby=name"
            response = self._make_request(endpoint)
            campaigns = response.get('value', [])
            
            # Add Convention 2025 - San Francisco for testing (even if closed or has parent)
            test_campaign_name = "Convention 2025 - San Francisco"
            
            # Check if it's already in the list
            has_test_campaign = any(c.get('name') == test_campaign_name for c in campaigns)
            
            if not has_test_campaign:
                # Query for the specific test campaign
                filter_clause = f"name eq '{test_campaign_name}'"
                test_endpoint = f"campaigns?$filter={urllib.parse.quote(filter_clause)}&$select=campaignid,name,_aha_parentcampaign_value"
                test_response = self._make_request(test_endpoint)
                test_campaigns = test_response.get('value', [])
                
                if test_campaigns:
                    campaigns.append(test_campaigns[0])
                    logger.info(f"Added test campaign: {test_campaign_name}")
            
            # Sort by name
            campaigns.sort(key=lambda c: c.get('name', ''))
            
            # Return simplified structure (only campaigns without parent, plus test campaign)
            return [
                {
                    'id': campaign.get('campaignid'),
                    'name': campaign.get('name')
                }
                for campaign in campaigns
            ]
            
        except Exception as e:
            logger.error(f"Error fetching open campaigns: {e}")
            raise
    
    @cache_with_ttl(ttl_seconds=300)
    def get_sub_events(self, parent_campaign_id: str) -> List[Dict[str, str]]:
        """
        Get list of sub-events (campaigns with a specific parent campaign).
        Cached for 5 minutes to reduce API calls.
        
        Args:
            parent_campaign_id: The ID of the parent campaign
            
        Returns:
            List of dictionaries with 'id' and 'name' keys
        """
        try:
            import urllib.parse
            
            # Query for campaigns that have this campaign as their parent
            filter_clause = f"_aha_parentcampaign_value eq {parent_campaign_id}"
            endpoint = f"campaigns?$filter={urllib.parse.quote(filter_clause)}&$select=campaignid,name,_aha_parentcampaign_value&$orderby=name"
            response = self._make_request(endpoint)
            sub_events = response.get('value', [])
            
            logger.info(f"Found {len(sub_events)} sub-events for campaign {parent_campaign_id}")
            
            # Return simplified structure
            return [
                {
                    'id': event.get('campaignid'),
                    'name': event.get('name')
                }
                for event in sub_events
            ]
            
        except Exception as e:
            logger.error(f"Error fetching sub-events for campaign {parent_campaign_id}: {e}")
            raise
    
    def get_campaign_by_name(self, campaign_name: str) -> Optional[Dict[str, str]]:
        """
        Get campaign by name.
        
        Args:
            campaign_name: Name of the campaign to find
            
        Returns:
            Dictionary with 'id' and 'name' keys, or None if not found
        """
        try:
            import urllib.parse
            filter_clause = f"name eq '{campaign_name}'"
            endpoint = f"campaigns?$filter={urllib.parse.quote(filter_clause)}&$select=campaignid,name"
            response = self._make_request(endpoint)
            campaigns = response.get('value', [])
            
            if campaigns:
                return {
                    'id': campaigns[0].get('campaignid'),
                    'name': campaigns[0].get('name')
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching campaign by name: {e}")
            raise
    
    def get_campaign_by_id(self, campaign_id: str) -> Optional[Dict[str, str]]:
        """
        Get campaign by ID.
        
        Args:
            campaign_id: GUID of the campaign
            
        Returns:
            Dictionary with 'id' and 'name' keys, or None if not found
        """
        try:
            endpoint = f"campaigns({campaign_id})?$select=campaignid,name"
            response = self._make_request(endpoint)
            
            return {
                'id': response.get('campaignid'),
                'name': response.get('name')
            }
            
        except Exception as e:
            logger.error(f"Error fetching campaign by ID: {e}")
            return None
    
    def download_data_by_type_filtered(self, data_type: str, view_id: str, campaign_id: str) -> pd.DataFrame:
        """
        Download data based on the type, filtered by campaign (main event + sub-events).
        
        Args:
            data_type: Type of data to download
            view_id: View ID (not used when filtering by campaign)
            campaign_id: GUID of the main campaign/event
            
        Returns:
            DataFrame with filtered data
        """
        logger.info(f"Downloading {data_type} for campaign {campaign_id}")
        
        try:
            if data_type == "event_guests":
                return self._get_event_guests_filtered(campaign_id)
            elif data_type == "qr_codes":
                # QR codes don't have direct campaign link, return all
                return self.get_qr_codes(view_id)
            elif data_type == "table_reservations":
                return self._get_table_reservations_filtered(campaign_id)
            elif data_type == "form_responses":
                return self._get_form_responses_filtered(campaign_id)
            else:
                raise ValueError(f"Unknown data type: {data_type}")
                
        except Exception as e:
            logger.error(f"Error downloading {data_type} for campaign: {e}")
            raise
    
    def _get_event_guests_filtered(self, campaign_id: str) -> pd.DataFrame:
        """Fetch event guests filtered by campaign (main + sub-events)."""
        import urllib.parse
        
        # Filter: Event is the main campaign OR Event's parent is the main campaign
        # Note: crca7_Event links to campaign entity, so use campaignid
        filter_clause = f"crca7_Event/campaignid eq {campaign_id} or crca7_Event/_aha_parentcampaign_value eq {campaign_id}"
        # Expand with all contact fields to ensure lookup fields (_aha_localclub2_value) are included
        # When you use $select in $expand, lookup fields may not be included automatically
        expand_query = "$expand=crca7_ExistingContact,crca7_Event($select=name)"
        
        endpoint = f"crca7_eventguests?$filter={urllib.parse.quote(filter_clause)}&{expand_query}"
        response = self._make_request(endpoint)
        df = self._process_response(response, "crca7_")
        
        df = self._flatten_expanded_columns(df)
        df = self._map_event_guest_columns(df)
        
        logger.info(f"Fetched {len(df)} event guests for campaign")
        return df
    
    def _get_table_reservations_filtered(self, campaign_id: str) -> pd.DataFrame:
        """Fetch table reservations filtered by campaign (main + sub-events)."""
        import urllib.parse
        
        # Filter: Event is the main campaign OR Event's parent is the main campaign
        filter_clause = f"aha_Event/campaignid eq {campaign_id} or aha_Event/_aha_parentcampaign_value eq {campaign_id}"
        expand_query = "$expand=aha_Contact($select=contactid),aha_Event($select=name),aha_Table($select=aha_name)"
        
        endpoint = f"aha_tablereservations?$filter={urllib.parse.quote(filter_clause)}&{expand_query}"
        response = self._make_request(endpoint)
        df = self._process_response(response, "aha_")
        
        df = self._flatten_seating_columns(df)
        df = self._map_seating_columns(df)
        
        logger.info(f"Fetched {len(df)} table reservations for campaign")
        return df
    
    def _get_form_responses_filtered(self, campaign_id: str) -> pd.DataFrame:
        """Fetch form responses filtered by campaign (main + sub-events)."""
        import urllib.parse
        
        # Filter: Campaign is the main campaign OR Campaign's parent is the main campaign
        filter_clause = f"aha_Campaign/campaignid eq {campaign_id} or aha_Campaign/_aha_parentcampaign_value eq {campaign_id}"
        expand_query = "$expand=aha_Contact($select=contactid),aha_Campaign($select=name),aha_FormQuestion($select=aha_newcolumn)"
        
        endpoint = f"aha_eventformresponseses?$filter={urllib.parse.quote(filter_clause)}&{expand_query}"
        response = self._make_request(endpoint)
        df = self._process_response(response, "aha_")
        
        df = self._flatten_form_response_columns(df)
        df = self._map_form_response_columns(df)
        
        logger.info(f"Fetched {len(df)} form responses for campaign")
        return df 