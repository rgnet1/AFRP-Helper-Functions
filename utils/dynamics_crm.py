import os
import json
import msal
import requests
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

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
            "OData-Version": "4.0"
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
        """Fetch event guests data."""
        endpoint = f"crca7_eventguests?$select=crca7_name,crca7_email,crca7_phonenumber,crca7_badgetype,crca7_company"
        response = self._make_request(endpoint)
        return self._process_response(response, "crca7_")

    def get_qr_codes(self, view_id: str) -> pd.DataFrame:
        """Fetch QR codes data."""
        endpoint = f"aha_eventguestqrcodes?$select=aha_name,aha_qrcode,aha_eventguest"
        response = self._make_request(endpoint)
        return self._process_response(response, "aha_")

    def get_table_reservations(self, view_id: str) -> pd.DataFrame:
        """Fetch table reservations data."""
        endpoint = f"aha_tablereservation?$select=aha_name,aha_tablenumber,aha_guestcount,aha_eventguest"
        response = self._make_request(endpoint)
        return self._process_response(response, "aha_")

    def get_form_responses(self, view_id: str) -> pd.DataFrame:
        """Fetch form responses data."""
        endpoint = f"aha_eventformresponses?$select=aha_name,aha_response,aha_eventguest"
        response = self._make_request(endpoint)
        return self._process_response(response, "aha_")

    def _process_response(self, response: Dict, prefix: str) -> pd.DataFrame:
        """Process the API response into a DataFrame."""
        records = response.get("value", [])
        df = pd.DataFrame(records)
        
        # Clean up column names
        if not df.empty:
            df.columns = [col.replace(prefix, "") for col in df.columns]
        
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