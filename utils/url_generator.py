import urllib.parse

# Constants for URL generation
ENV_PROD = "https://my.afrp.org/"
ENV_DEV = "https://afrpdev.powerappsportals.com/"
CURRENT_ENV = ENV_PROD

def generate_event_registration_url(event_id: str) -> str:
    """Generate the event registration URL for a given event ID."""
    return f"{CURRENT_ENV}Event_registration/event/?id={event_id}"

def generate_event_summary_url(event_id: str) -> str:
    """Generate the event summary URL for a given event ID."""
    return f"{CURRENT_ENV}eventsummary/?id={event_id}"

def extract_event_id(crm_url: str) -> str:
    """Extract event ID from a CRM URL.
    
    Args:
        crm_url: The CRM event page URL
        
    Returns:
        The extracted event ID or None if not found
        
    Raises:
        ValueError: If the URL is invalid or missing event ID
    """
    try:
        parsed_url = urllib.parse.urlparse(crm_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        event_id = query_params.get('id', [None])[0]
        
        if not event_id:
            raise ValueError('Event ID not found in URL')
            
        return event_id
    except Exception as e:
        raise ValueError(f'Invalid URL: {str(e)}')
