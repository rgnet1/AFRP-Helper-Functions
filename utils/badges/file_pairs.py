import os
import re
from datetime import datetime, timedelta
import difflib

def get_most_recent_pair():
    # Get all .xlsx files in the current directory
    files = [f for f in os.listdir('.') if f.endswith('.xlsx')]

    def parse_filename(filename):
        # Remove the file extension
        name = os.path.splitext(filename)[0]

        # Regex pattern to extract event name, event type, date, and time
        # Pattern: Event Name Event Type Date Time AM/PM
        pattern = r'^(?P<event_name>.*?) (?P<event_type>Registration List|Seating Chart) (?P<date>\d{1,2}-\d{1,2}-\d{4}) (?P<time>\d{1,2}-\d{1,2}-\d{1,2} [AP]M)$'
        match = re.match(pattern, name)
        if match:
            event_name = match.group('event_name').strip()
            event_type = match.group('event_type')
            date_str = match.group('date')
            time_str = match.group('time')

            # Parse the datetime object
            try:
                dt = datetime.strptime(date_str + ' ' + time_str, '%m-%d-%Y %I-%M-%S %p')
            except ValueError:
                return None

            return {
                'filename': filename,
                'event_name': event_name,
                'event_type': event_type,
                'datetime': dt
            }
        else:
            return None

    # Lists to store registration and seating chart files
    registration_files = []
    seating_chart_files = []

    # Parse each file and categorize them
    for f in files:
        info = parse_filename(f)
        if info:
            if info['event_type'] == 'Registration List':
                registration_files.append(info)
            elif info['event_type'] == 'Seating Chart':
                seating_chart_files.append(info)

    pairs = []

    # For each registration file, find the best matching seating chart file
    for reg_file in registration_files:
        reg_event_name = reg_file['event_name']
        reg_dt = reg_file['datetime']
        best_match = None
        highest_similarity = 0
        min_time_diff = timedelta.max

        for sc_file in seating_chart_files:
            sc_event_name = sc_file['event_name']
            sc_dt = sc_file['datetime']

            # Compute similarity between event names
            similarity = difflib.SequenceMatcher(None, reg_event_name.lower(), sc_event_name.lower()).ratio()

            if similarity > highest_similarity:
                time_diff = abs(reg_dt - sc_dt)
                best_match = sc_file
                highest_similarity = similarity
                min_time_diff = time_diff
            elif similarity == highest_similarity:
                # If similarity is equal, pick the one with the smallest time difference
                time_diff = abs(reg_dt - sc_dt)
                if time_diff < min_time_diff:
                    best_match = sc_file
                    min_time_diff = time_diff

        if best_match:
            pairs.append({
                'registration_file': reg_file['filename'],
                'seating_chart_file': best_match['filename'],
                'datetime': reg_dt
            })

    # Select the most recent complete pair
    if pairs:
        pairs.sort(key=lambda x: x['datetime'], reverse=True)
        most_recent_pair = pairs[0]
        return most_recent_pair['registration_file'], most_recent_pair['seating_chart_file']
    else:
        return None, None

# Example usage:
# registration_file, seating_chart_file = get_most_recent_pair()
# print("Most recent registration file:", registration_file)
# print("Associated seating chart file:", seating_chart_file)
