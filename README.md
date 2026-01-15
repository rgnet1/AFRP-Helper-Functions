# AFRP CRM Helper

A comprehensive web application for AFRP (American Federation of Ramallah, Palestine) providing automated tools for event management, badge generation, and content distribution.

## Features

### 🎫 Badge Generator
Automated badge generation system with Dynamics 365 CRM integration:
- **Automated Data Pulling**: Direct integration with Dynamics CRM - no manual exports needed
- **Intelligent Processing**: Database-driven preprocessing with user-configurable templates
- **Professional Badges**: SVG-based customizable templates with QR codes
- **Avery Label Support**: Print-ready PDFs for multiple Avery sheet sizes
- **Template Designer**: Visual interface for badge design and column mapping

**Key Capabilities**:
- Pull attendee data from 4 Dynamics entities automatically
- Apply custom data transformations via Preprocessing Designer
- Generate QR codes for each attendee
- Map Excel columns to badge placeholders visually
- Support for sub-events, table assignments, and custom fields
- Export to PDF ready for printing on Avery labels

### 📖 Magazine Downloader
Automated magazine distribution system:
- **Scheduled Downloads**: Automatic magazine retrieval from Dropbox
- **Progress Tracking**: Real-time download monitoring
- **Error Handling**: Robust logging and retry mechanisms
- **CRM Upload**: Automatic upload to AFRP CRM

### 🔗 Event URL Generator
Generate event-specific URLs:
- Event registration URLs
- Event summary URLs
- Input validation and error handling

### 📱 QR Code Generator
Generate QR codes for various purposes:
- Customizable size and format
- Batch processing capability
- Multiple export options

## Architecture

### Technology Stack
- **Backend**: Flask (Python)
- **Database**: SQLite with SQLAlchemy ORM
- **CRM Integration**: Dynamics 365 Web API with OAuth 2.0
- **Badge Generation**: ReportLab, svglib, cairosvg
- **Task Scheduling**: APScheduler
- **Containerization**: Docker

### Key Components
- **app.py**: Main Flask application with routing and API endpoints
- **utils/dynamics_crm.py**: Dynamics 365 CRM client with OAuth authentication
- **utils/badges/**: Badge generation and data processing modules
- **templates/**: HTML templates for web interface
- **badge_templates/**: User-uploaded SVG badge templates
- **data/**: SQLite database for schedules and configurations

## Installation

### Using Docker Compose (Recommended)

1. **Clone the repository**:
```bash
git clone <repository-url>
cd qr_code_generator
```

2. **Configure environment variables**:
Create `config/.env` with your Dynamics CRM credentials:
```bash
DYNAMICS_TENANT_ID=your-tenant-id
DYNAMICS_CLIENT_ID=your-client-id
DYNAMICS_CLIENT_SECRET=your-client-secret
DYNAMICS_CRM_URL=https://yourorg.crm.dynamics.com
```

3. **Start the application**:
```bash
docker-compose up -d --build
```

4. **Access the application**:
Navigate to `http://localhost:5066`

### Manual Installation

1. **Prerequisites**:
   - Python 3.10+
   - pip
   - virtualenv (recommended)

2. **Setup**:
```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

## Configuration

### Required Directories
The application uses these directories (created automatically):
- `config/`: Configuration files and credentials
- `downloads/`: Magazine download storage
- `logs/`: Application logs with rotation
- `data/`: SQLite database
- `badge_templates/`: User-uploaded badge SVG templates
- `badge_logos/`: User-uploaded club logos
- `temp/`: Temporary processing files
- `instance/`: Flask instance folder

### Dynamics CRM Setup

1. **Azure AD App Registration**:
   - Register an application in Azure AD
   - Note the Client ID and Tenant ID
   - Create a client secret

2. **Application User in Dynamics 365**:
   - Create an Application User in Dynamics 365
   - Link it to your Azure AD app (Client ID)
   - Assign appropriate security roles:
     - Read access to Event Guests, QR Codes, Seating Tables, Form Responses
     - Or System Administrator for testing

3. **Environment Variables**:
   Add to `config/.env`:
   ```
   DYNAMICS_TENANT_ID=<your-tenant-id>
   DYNAMICS_CLIENT_ID=<your-client-id>
   DYNAMICS_CLIENT_SECRET=<your-secret>
   DYNAMICS_CRM_URL=https://yourorg.crm.dynamics.com
   ```

### Authentication

The application includes a secure authentication system to protect access.

#### First-Time Setup

1. **Generate a SECRET_KEY**:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

2. **Add it to `config/.env`**:
   ```bash
   SECRET_KEY=your-generated-key-here
   ```

3. **Start the application** and visit `/setup` to create your admin account

#### Security Features

- Server-side bcrypt password hashing (cost factor 12)
- Session management with HttpOnly, Secure cookies
- Rate limiting (5 login attempts per 15 minutes)
- Password requirements (min 8 chars, uppercase, lowercase, number, special char)
- Remember me functionality (30-day sessions)
- Admin-only user management interface

#### User Management

Admins can manage users at `/users`:
- Create new user accounts
- Toggle user active/inactive status
- Delete users (except self)
- View login history

### Docker Configuration
Default `docker-compose.yaml` settings:
- Port: 5066 (external) → 5000 (internal)
- Timezone: America/Los_Angeles
- Auto-restart: unless-stopped

## Usage

### Badge Generation Workflow

1. **Access Badge Generator**: Navigate to `/badges`

2. **Select Campaign**: Choose your main event from the dropdown

3. **Configure Preprocessing** (optional):
   - Click "Designer" to open Preprocessing Designer
   - Create data transformation rules (e.g., shorten meal preferences)
   - Save template for reuse

4. **Configure Badge Template** (first time):
   - Click "Configure Templates" to open Badge Mapping Designer
   - Upload SVG template with placeholders like `{{FIRST_NAME}}`
   - Map each placeholder to Excel column
   - Upload club logo (optional)
   - Select Avery template size
   - Save template

5. **Generate Badges**:
   - Option A: Click "Pull, Process & Generate Badges" (one-click)
   - Option B: Click "Pull All & Process" first, then "Generate Badges from Processed Data"

6. **Print**: Download PDF and print on Avery label sheets

### Preprocessing Designer

Create custom data transformation rules without code:

**Value Mappings** (exact replacements):
- "Steak" → "S"
- "Chicken" → "C"
- "No Club Affiliation" → " "

**Contains Mappings** (substring removal):
- "- Reserved" → ""
- "Ramallah Federation in " → ""

Templates are saved to database and reusable across events.

### Badge Template Designer

Visual interface for mapping spreadsheet columns to badge placeholders:

**Available Placeholders**:
- `{{FIRST_NAME}}`, `{{LAST_NAME}}` - Attendee name
- `{{MEMBER_ID}}` - Member ID (ID-####)
- `{{LOCAL_CLUB}}` - Club affiliation
- `{{QR_CODE}}` - Auto-generated QR code
- `{{TABLE_NUMBER}}` - Table assignment
- `{{SUBEVENT_1}}`, `{{SUBEVENT_2}}` - Sub-event registrations
- `{{AFRP_LOGO}}`, `{{CLUB_LOGO}}` - Logo images

### Magazine Downloader

1. Navigate to `/magazine`
2. Configure Dropbox credentials
3. Set download schedule
4. Monitor progress in logs

## Backup & Restore

Complete system backup and restore capability for data protection and migration.

### Quick Backup

```bash
# Create compressed backup
docker-compose exec afrp-helper python3 backup/backup.py --compress

# Or use bash wrapper
./backup/backup.sh --compress
```

### Quick Restore

```bash
# Stop application
docker-compose down

# Restore from backup
docker-compose exec afrp-helper python3 backup/restore.py afrp_backup_20260115_120000

# Start application
docker-compose up -d
```

### What Gets Backed Up

✅ **Database**: Users, schedules, templates, all configurations  
✅ **Badge Templates**: User-uploaded SVG files  
✅ **Badge Logos**: Club logos and images  
✅ **Configuration**: Non-sensitive config files  

**Note**: `.env` files excluded (sensitive credentials)

### Safety Features

- Automatic pre-restore safety backup
- Database integrity verification
- Dry-run mode for testing
- Detailed backup manifests

📖 **Full Documentation**: See `.cursor/rules/backup-restore-system.mdc` for:
- Detailed usage instructions
- Best practices
- Recovery scenarios
- Migration guides
- Troubleshooting

## API Endpoints

### Badge Generation
- `GET /badges` - Badge Generator UI
- `POST /api/badges/pull-and-process` - Pull and process CRM data
- `POST /api/badges/generate` - Generate PDF badges
- `POST /api/badges/pull-process-generate` - Complete workflow

### Template Management
- `GET /api/badge-templates` - List badge templates
- `POST /api/badge-templates` - Create badge template
- `PUT /api/badge-templates/<id>` - Update badge template
- `DELETE /api/badge-templates/<id>` - Delete badge template
- `POST /api/badge-templates/<id>/duplicate` - Duplicate template

### Preprocessing
- `GET /api/preprocessing-templates` - List preprocessing templates
- `POST /api/preprocessing-templates` - Create preprocessing template
- `PUT /api/preprocessing-templates/<id>` - Update preprocessing template
- `DELETE /api/preprocessing-templates/<id>` - Delete preprocessing template
- `POST /api/preprocessing-templates/<id>/duplicate` - Duplicate template

### Campaign Data
- `GET /api/campaigns` - List available campaigns
- `GET /api/campaigns/<id>/sub-events` - Get sub-events for campaign

## Development

### Project Structure
```
qr_code_generator/
├── app.py                      # Main Flask application
├── utils/
│   ├── dynamics_crm.py         # Dynamics CRM client
│   ├── badges/
│   │   ├── badge_generator.py  # PDF badge generation
│   │   ├── convert_to_mail_merge_v3.py  # Data processing
│   │   ├── pre_processing_module.py     # Preprocessing base
│   │   └── event_preprocessing/         # Reference examples (deprecated)
│   └── magazine/               # Magazine download modules
├── templates/                  # HTML templates
├── static/                     # Static assets (CSS, JS, images)
├── badge_templates/            # User-uploaded badge templates
├── .cursor/rules/              # AI coding assistant rules
└── docker-compose.yaml         # Docker configuration
```

### Testing Dynamics CRM Connection

Run the validation script:
```bash
python test_dynamics_access.py
```

This tests:
- OAuth token acquisition
- API connectivity
- Access to all 4 required entities
- Formatted value extraction

### Database Migrations

Database migrations run **automatically** at container startup. The system:
- ✅ Detects pending schema changes
- ✅ Applies migrations in order
- ✅ Tracks applied migrations
- ✅ Skips already-applied migrations (idempotent)

**Database Models**: `utils/magazine/scheduler.py`
- User, Schedule, BadgeTemplate, PreprocessingTemplate, EventViewConfig, JobRun

**Migration Files**: `db_migrations/migrations/`
- `001_create_user_table.py` - User authentication table
- `002_add_club_logo_dimensions.py` - Badge template enhancements

**Creating New Migrations**:
```bash
# Create migration file: db_migrations/migrations/003_your_change.py
# See db_migrations/README.md for detailed instructions

# Test locally
python3 db_migrations/migration_runner.py --dry-run
python3 db_migrations/migration_runner.py

# Deploy - migrations run automatically on container restart
docker-compose up -d --build
```

For detailed migration documentation, see `db_migrations/README.md` or `.cursor/rules/database-migrations.mdc`.

## Troubleshooting

### 403 Forbidden Errors
**Issue**: Cannot access Dynamics CRM entities

**Solution**:
1. Verify Application User exists in Dynamics 365
2. Check security roles are assigned
3. Ensure Azure AD app has correct permissions
4. Run `python test_dynamics_access.py` to diagnose

See `.cursor/rules/dynamics-troubleshooting.mdc` for detailed troubleshooting.

### 404 Not Found Errors
**Issue**: Wrong entity name in API calls

**Solution**: Dynamics uses EntitySetName (collection name), not LogicalName:
- `crca7_eventguest` → `crca7_eventguests`
- `aha_eventguestqrcodes` → `aha_eventguestqrcodeses`

### Blank PDF Badges
**Issue**: Generated PDF is empty

**Common causes**:
1. SVG template file missing
2. Badge template folder not mounted in Docker
3. Incorrect column mappings

**Solution**:
- Verify `badge_templates/` volume is mounted
- Check SVG file exists in container
- Validate column mappings in Badge Mapping Designer

### Missing Columns in Output
**Issue**: Expected column not in processed Excel

**Solution**:
- Check Dynamics CRM field names
- Verify `$expand` queries include related entities
- Use `.cursor/skills/dynamics-column-discovery/SKILL.md` for guidance

## Logs

Application logs are stored in `logs/` with automatic rotation:
- **scheduler.log**: Scheduler events (1MB max, 5 backups)
- **jobs.log**: Job execution logs (1MB max, 5 backups)
- **magazine.log**: Magazine download logs

View logs:
```bash
# Docker
docker-compose logs -f afrp-helper

# Local
tail -f logs/scheduler.log
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Documentation

Additional documentation available in `.cursor/rules/`:
- `badge-generation.mdc` - Badge generation system
- `badge-templates.mdc` - Template management
- `preprocessing-system.mdc` - Data preprocessing
- `dynamics-troubleshooting.mdc` - CRM integration issues
- `avery-layouts.mdc` - Label specifications
- `browser-features.mdc` - UI features

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues or questions:
1. Check `.cursor/rules/` documentation
2. Review troubleshooting section above
3. Run `test_dynamics_access.py` for CRM issues
4. Check Docker logs for errors
5. Open an issue on GitHub
