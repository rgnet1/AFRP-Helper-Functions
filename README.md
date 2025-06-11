# AFRP Helper Functions

A comprehensive web application designed to assist AFRP administrators with various automation tasks and tools.

## Features

### 1. QR Code Generator
- Generate QR codes with custom text/URLs
- Option to include custom images in QR codes
- Download generated QR codes for use in marketing materials

### 2. Magazine Downloader
- Automated magazine download functionality
- Configurable download schedules (daily, weekly, monthly)
- Real-time progress tracking with console output
- Secure storage of downloaded magazines
- Integration with Dropbox for file management
- Persistent job history and error logging
- Timezone-aware scheduling (America/Los_Angeles)

### 3. Event URL Generator
- Generate registration and summary URLs for events
- Easy copy-to-clipboard functionality
- Input validation for CRM event URLs
- Mobile-responsive interface

### 4. Badge Generator
- Generate event badges from registration data
- Support for main events and sub-events
- Automatic QR code integration
- Customizable badge layouts
- Handles multiple input files:
  - Registration List
  - Seating Chart
  - QR Codes
  - Form Responses
- Smart filtering for sub-event specific badges
- Exports to mail merge ready format

## Installation

### Docker
```bash
docker pull rgnet1/afrp-helper:latest
docker run -p 5066:5000 \
  -v /path/to/config:/config \
  -v /path/to/downloads:/app/downloads \
  -v /path/to/logs:/app/logs \
  rgnet1/afrp-helper:latest
```

### Docker Compose
```yaml
services:
  afrp-helper:
    image: rgnet1/afrp-helper:latest
    ports:
      - "5066:5000"
    volumes:
      - ./config:/config
      - magazine_downloads:/app/downloads
      - magazine_logs:/app/logs
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped

volumes:
  magazine_downloads:
  magazine_logs:
```

### Unraid
1. Add the following template URL to your Unraid server:
   ```
   https://raw.githubusercontent.com/rgnet1/AFRP-Helper-Functions/master/template/AFRP_helper.xml
   ```
2. Find "AFRP Helper" in the Apps section
3. Configure the container paths and port
4. Click Apply

## Configuration

### Required Directories
- `/config`: Configuration files
- `/app/downloads`: Magazine download storage
- `/app/logs`: Application logs
  - `scheduler.log`: Scheduler events (job additions, removals)
  - `jobs.log`: Individual job execution logs
  - Both logs use rotation (1MB size limit, keeps last 5 files)

### Environment Variables
- `PYTHONUNBUFFERED=1`: Ensures real-time logging (recommended)
- `TZ=America/Los_Angeles`: Container timezone (defaults to Los Angeles)

### Database
The application uses SQLite for storing:
- Magazine download schedules
- Job execution history
- Error logs and status information

The database is automatically initialized on first run and persisted in the `magazine_db` volume.

## Usage

1. Access the web interface at `http://localhost:5066` (or your server's IP)
2. Choose the desired tool from the home page:
   - QR Code Generator: Create custom QR codes
   - Magazine Downloader: Download and manage magazines
   - Event URL Generator: Generate event registration links
   - Badge Generator: Create event badges and name tags

### Using the Badge Generator

1. **Prepare Your Files**
   - Registration List (Excel file with registration data)
   - Seating Chart (Excel file with seating assignments)
   - QR Codes (Excel file with QR code data)
   - Form Responses (Excel file with additional form data)

2. **Upload Files**
   - Drag and drop your files into the upload area
   - Or click to select files manually
   - The system will automatically validate and categorize your files

3. **Select Event Options**
   - Choose the main event from the dropdown
   - Optionally select a specific sub-event
   - For sub-events, the system will automatically:
     - Filter for registered attendees only
     - Include relevant form fields
     - Maintain proper column structure

4. **Generate Badges**
   - Click "Process Files" to generate the mail merge file
   - The system will combine all data and create a properly formatted Excel file
   - Download the resulting file for use with your badge printing software

## Development

### Prerequisites
- Python 3.10+
- Required packages listed in requirements.txt

### Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/rgnet1/AFRP-Helper-Functions.git
   cd AFRP-Helper-Functions
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the development server:
   ```bash
   python app.py
   ```

## Support

For issues, feature requests, or contributions, please visit:
https://github.com/rgnet1/AFRP-Helper-Functions
