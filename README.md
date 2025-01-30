# AFRP Helper Functions

A comprehensive web application designed to assist AFRP administrators with various automation tasks and tools.

## Features

### 1. QR Code Generator
- Generate QR codes with custom text/URLs
- Option to include custom images in QR codes
- Download generated QR codes for use in marketing materials

### 2. Magazine Downloader
- Automated magazine download functionality
- Real-time progress tracking with console output
- Secure storage of downloaded magazines
- Integration with Dropbox for file management

### 3. Event URL Generator
- Generate registration and summary URLs for events
- Easy copy-to-clipboard functionality
- Input validation for CRM event URLs
- Mobile-responsive interface

## Installation

### Docker
```bash
docker pull rgnet1/afrp-helper:latest
docker run -p 5000:5000 \
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
      - "5000:5000"
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

### Environment Variables
- `PYTHONUNBUFFERED=1`: Ensures real-time logging (recommended)

## Usage

1. Access the web interface at `http://localhost:5000` (or your server's IP)
2. Choose the desired tool from the home page:
   - QR Code Generator: Create custom QR codes
   - Magazine Downloader: Download and manage magazines
   - Event URL Generator: Generate event registration links

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
