# AFRP Helper Functions

This repository contains helper functions for AFRP CRM, including:
- QR Code Generator
- Magazine Downloader
- Event URL Generator
- Badge Generator

## Features

### QR Code Generator
- Generate QR codes for various purposes
- Customizable size and format
- Batch processing capability

### Magazine Downloader
- Automated magazine download scheduling
- Progress tracking
- Error handling and logging
- Automatic upload to AFRP CRM

### Event URL Generator
- Generate event registration URLs
- Generate event summary URLs
- Input validation and error handling

### Badge Generator
- Process registration lists
- Generate name badges
- Support for multiple event types

## Installation

### Using Docker

1. Build the image:
```bash
docker build -t afrp-helper .
```

2. Run the container:
```bash
docker run -p 5066:5000 \
  -v /path/to/config:/config \
  -v /path/to/downloads:/app/downloads \
  -v /path/to/logs:/app/logs \
  afrp-helper
```

### Using Docker Compose

1. Create a `docker-compose.yml`:
```yaml
version: '3'
services:
  afrp-helper:
    image: afrp-helper:latest
    ports:
      - "5066:5000"
    volumes:
      - /path/to/config:/config
      - /path/to/downloads:/app/downloads
      - /path/to/logs:/app/logs
```

2. Start the service:
```bash
docker-compose up -d
```

## Usage

1. Access the web interface at `http://localhost:5066`
2. Choose the desired tool:
   - QR Code Generator
   - Magazine Downloader
   - Event URL Generator
   - Badge Generator

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

The database is automatically initialized on first run and persisted in the `/app/data` volume.

## Development

### Prerequisites
- Python 3.8+
- pip
- virtualenv (recommended)

### Setup
1. Clone the repository
2. Create and activate virtual environment
3. Install dependencies: `pip install -r requirements.txt`
4. Run the application: `python app.py`

### Testing
Run tests with: `python -m pytest tests/`

## Contributing
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License
This project is licensed under the MIT License - see the LICENSE file for details.
