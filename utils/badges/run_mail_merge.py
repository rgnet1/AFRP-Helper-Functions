import os
import sys
import argparse
import pandas as pd

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.badges.convert_to_mail_merge_v3 import main

def get_available_events():
    """Get list of available events from registration data."""
    # Find the latest registration file
    files = [f for f in os.listdir('.') if f.endswith('.xlsx') and 'Registration List' in f]
    if not files:
        print("Error: No registration file found")
        sys.exit(1)
    
    latest_file = max(files)  # This works because the filenames include timestamps
    
    # Read the registration data
    df = pd.read_excel(latest_file)
    
    # Get unique events from paid registrations
    events = df[df['Status Reason'] == 'Paid']['Event '].unique()
    return sorted(events)

def parse_args():
    parser = argparse.ArgumentParser(description='Generate mail merge files for convention badges')
    parser.add_argument('--sub-event', type=str, help='Generate mail merge for a specific sub-event')
    parser.add_argument('--list-events', action='store_true', help='List all available events')
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    if args.list_events:
        print("\nAvailable events from registration data:\n")
        for event in get_available_events():
            print(f"  - {event}")
        sys.exit(0)
    
    main(args.sub_event) 