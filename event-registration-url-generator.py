import urllib.parse
ENV_PROD = "https://my.afrp.org/"
ENV_DEV = "https://afrpdev.powerapps.com_CHECK_ME"
CURRENT_ENV = ENV_PROD

def generate_event_registration_url(event_id):
    return f"{CURRENT_ENV}Event_registration/event/?id={event_id}"

def generate_event_summary_url(event_id):
     # Construct the event registration URL
    return f"{CURRENT_ENV}eventsummary/?id={event_id}"

def generate_event_id(crm_url):
    # Parse the input URL
    parsed_url = urllib.parse.urlparse(crm_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    # Extract the 'id' parameter value
    event_id = query_params.get('id', [None])[0]

    # Check if the 'id' parameter was found
    if event_id:
       return event_id
    else:
        return "Invalid URL: 'id' parameter not found."

# Prompt the user for the CRM URL
input_url = input("Enter the CRM Event Page URL: ")
event_id = generate_event_id(input_url)
event_url = generate_event_registration_url(event_id)
event_summary_url = generate_event_summary_url(event_id)
print()
print("Event URL:\n", event_url)
print("Summary Page URL:", event_summary_url)
