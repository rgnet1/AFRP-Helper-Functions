# Badge Generation Feature - Implementation Status

## Date: January 12, 2026

## ✅ COMPLETED

### 1. Dependencies Added
- **File**: `requirements.txt`
- **Added**:
  - `reportlab>=4.0.0` - PDF generation
  - `svglib>=1.5.1` - SVG to PDF conversion
  - `cairosvg>=2.7.0` - Alternative SVG renderer

### 2. Database Model Created
- **File**: `utils/magazine/scheduler.py`
- **Model**: `BadgeTemplate`
  - Stores template configurations
  - Fields: name, svg_filename, column_mappings (JSON), avery_template, timestamps
  - Includes `to_dict()` method for JSON serialization

### 3. Badge Generator Module Created
- **File**: `utils/badges/badge_generator.py`
- **Features**:
  - `BadgeGenerator` class with full functionality
  - Avery template specifications for 4 common sizes (5392, 5395, 8395, 74459)
  - QR code generation from string data
  - SVG template rendering with placeholder replacement
  - PDF generation with proper Avery sheet layout
  - Logo embedding (AFRP + club logos)
  - Helper methods for template discovery and placeholder extraction

### 4. API Endpoints Created
- **File**: `app.py`
- **Endpoints Added**:
  - `GET /api/badge-templates` - List all saved templates
  - `POST /api/badge-templates` - Create new template
  - `GET /api/badge-templates/<id>` - Get specific template
  - `PUT /api/badge-templates/<id>` - Update template
  - `DELETE /api/badge-templates/<id>` - Delete template
  - `POST /api/badge-templates/upload-svg` - Upload SVG template
  - `POST /api/badge-logos/upload` - Upload club logo
  - `GET /api/avery-templates` - List available Avery templates
  - `POST /api/badges/generate` - Generate PDF badges from Excel
  - `POST /api/badges-v2/pull-process-generate` - Combined workflow endpoint

### 5. Badge Mapping UI Created
- **File**: `templates/badge_mapping.html`
- **Features**:
  - Modern, responsive design with gradient background
  - SVG template upload with drag-and-drop
  - Club logo upload with drag-and-drop
  - Automatic placeholder extraction from SVG
  - Dropdown-based column mapping interface
  - Avery template selector
  - Save/load template configurations
  - List of saved templates with click-to-load

### 6. Configuration Updated
- **File**: `app.py`
- **Added**:
  - Import statements for `BadgeTemplate` and `BadgeGenerator`
  - `json` import
  - Directory creation for `badge_templates` and `badge_logos`
  - App config for `BADGE_TEMPLATES_FOLDER`, `BADGE_LOGOS_FOLDER`, `AFRP_LOGO_PATH`
  - Route for `/badge-mapping` page

## 🚧 REMAINING WORK

### 1. Update badges_v2.html UI
**Priority**: HIGH
**Tasks**:
- Add "Configure Badge Template" button linking to `/badge-mapping`
- Add "Generate Badges" section after data processing
- Add template selector dropdown (loads from saved templates)
- Add "Generate Badges Only" button (uses already processed Excel)
- Add "Process Data & Generate Badges" button (combined workflow)
- Update UI to show badge generation progress
- Add download link for generated PDF badges

**Suggested Implementation**:
```html
<!-- Add after the existing "Process Data" section -->
<div class="section">
    <h2>Badge Generation</h2>
    <div class="actions">
        <a href="/badge-mapping" class="btn btn-secondary">
            <i class="fas fa-cog"></i> Configure Badge Template
        </a>
        <select id="badgeTemplateSelect">
            <option value="">Select a badge template...</option>
        </select>
        <button id="generateBadgesBtn" class="btn btn-primary" disabled>
            <i class="fas fa-id-card"></i> Generate Badges
        </button>
        <button id="processAndGenerateBtn" class="btn btn-success">
            <i class="fas fa-rocket"></i> Process Data & Generate Badges
        </button>
    </div>
</div>
```

### 2. Create Default SVG Template
**Priority**: HIGH
**File**: `badge_templates/default_badge_template.svg`
**Requirements**:
- 3" x 4" dimensions (to fit Avery 5392)
- Placeholders:
  - `{{FIRST_NAME}}`
  - `{{LAST_NAME}}`
  - `{{MEMBER_ID}}`
  - `{{LOCAL_CLUB}}`
  - `{{TABLE_NUMBER}}`
  - `{{SUB_EVENTS}}`
  - `{{QR_CODE}}` (with position markers)
  - `{{AFRP_LOGO}}` (top left)
  - `{{CLUB_LOGO}}` (top right)
- Clean, professional design
- Text elements should be properly styled

**Sample SVG Structure**:
```svg
<svg xmlns="http://www.w3.org/2000/svg" width="288" height="384" viewBox="0 0 288 384">
  <!-- AFRP Logo (top left) -->
  <image x="10" y="10" width="60" height="60" href="{{AFRP_LOGO}}"/>
  
  <!-- Club Logo (top right) -->
  <image x="218" y="10" width="60" height="60" href="{{CLUB_LOGO}}"/>
  
  <!-- Name -->
  <text x="144" y="100" text-anchor="middle" font-size="24" font-weight="bold">{{FIRST_NAME}} {{LAST_NAME}}</text>
  
  <!-- Member ID -->
  <text x="144" y="130" text-anchor="middle" font-size="14">{{MEMBER_ID}}</text>
  
  <!-- Local Club -->
  <text x="144" y="155" text-anchor="middle" font-size="12">{{LOCAL_CLUB}}</text>
  
  <!-- Table Number -->
  <text x="20" y="200" font-size="12">Table: {{TABLE_NUMBER}}</text>
  
  <!-- Sub Events -->
  <text x="20" y="230" font-size="10">{{SUB_EVENTS}}</text>
  
  <!-- QR Code (bottom center) -->
  <image x="114" y="290" width="60" height="60" href="{{QR_CODE}}"/>
</svg>
```

### 3. Create/Add AFRP Logo
**Priority**: HIGH
**File**: `static/afrp_logo.png`
**Requirements**:
- PNG format with transparency
- Square or rectangular
- High resolution (at least 300x300px)
- Should match the logo shown in the user's image

### 4. Seed Default Badge Template
**Priority**: MEDIUM
**File**: `app.py`
**Task**: Add seeding logic in `app.app_context()` to create a default template
```python
with app.app_context():
    db.create_all()
    
    # Seed default badge template if it doesn't exist
    if not BadgeTemplate.query.filter_by(name='Default').first():
        default_template = BadgeTemplate(
            name='Default',
            svg_filename='default_badge_template.svg',
            column_mappings=json.dumps({
                '{{FIRST_NAME}}': 'First Name',
                '{{LAST_NAME}}': 'Last Name',
                '{{MEMBER_ID}}': 'Member ID',
                '{{LOCAL_CLUB}}': 'Local Club',
                '{{QR_CODE}}': 'QR Code'
            }),
            avery_template='5392'
        )
        db.session.add(default_template)
        db.session.commit()
        logger.info("Seeded default badge template")
```

### 5. Add JavaScript Functions to badges_v2.html
**Priority**: HIGH
**Functions Needed**:
- `loadBadgeTemplates()` - Fetch and populate template dropdown
- `generateBadges()` - Generate badges from processed Excel
- `processAndGenerateBadges()` - Combined workflow
- `updateBadgeGenerationUI()` - Enable/disable buttons based on state

### 6. Test & Debug
**Priority**: HIGH
**Tasks**:
- Test SVG upload and placeholder extraction
- Test column mapping interface
- Test template save/load
- Test logo upload
- Test PDF generation with real data
- Test Avery template layouts
- Test combined workflow
- Verify QR codes are readable
- Verify logos display correctly

### 7. Update Docker Configuration
**Priority**: MEDIUM
**File**: `Dockerfile`
**Tasks**:
- Ensure new dependencies are installed
- Verify badge_templates and badge_logos directories are created
- Test in Docker environment

## USAGE FLOW (Once Complete)

### Option A: Separate Workflow
1. User goes to Badge Generator V2
2. User processes data (pulls from CRM, generates Excel)
3. User clicks "Configure Badge Template" (if needed)
4. User maps columns to placeholders and saves template
5. User returns to Badge Generator V2
6. User selects template and clicks "Generate Badges"
7. User downloads PDF file

### Option B: Combined Workflow
1. User goes to Badge Generator V2
2. User configures template (one time)
3. User clicks "Process Data & Generate Badges"
4. System pulls data, processes, and generates badges in one go
5. User downloads PDF file

## KNOWN ISSUES & LIMITATIONS

1. **SVG Complexity**: Complex SVG files with gradients, filters, or advanced features may not render correctly in PDF
2. **Font Embedding**: Custom fonts in SVG may not be preserved - system fonts are safer
3. **Image Quality**: Logo quality depends on source image resolution
4. **Performance**: Generating badges for 500+ attendees may take 30-60 seconds
5. **Memory**: Large datasets may require more memory allocation

## NEXT STEPS

1. Complete badges_v2.html updates (highest priority)
2. Create default SVG template
3. Add AFRP logo image
4. Test end-to-end workflow
5. Fix any discovered issues
6. Document for user

## FILES MODIFIED/CREATED

### Modified:
- `/home/rumz/git/qr_code_generator/requirements.txt`
- `/home/rumz/git/qr_code_generator/utils/magazine/scheduler.py`
- `/home/rumz/git/qr_code_generator/app.py`

### Created:
- `/home/rumz/git/qr_code_generator/utils/badges/badge_generator.py`
- `/home/rumz/git/qr_code_generator/templates/badge_mapping.html`
- `/home/rumz/git/qr_code_generator/BADGE_GENERATION_IMPLEMENTATION_STATUS.md` (this file)

### Directories Created:
- `/home/rumz/git/qr_code_generator/badge_templates/`
- `/home/rumz/git/qr_code_generator/badge_logos/`

### Still Needed:
- `badge_templates/default_badge_template.svg`
- `static/afrp_logo.png`
- Updates to `templates/badges_v2.html`
