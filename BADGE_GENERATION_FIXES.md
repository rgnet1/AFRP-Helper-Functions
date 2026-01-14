# Badge Generation Fixes - January 14, 2026

## 🐛 Issues Found

### 1. **Missing Volume Mounts** ❌
The `badge_templates` and `badge_logos` folders were NOT mounted as Docker volumes.
- When you uploaded SVG templates through the UI, they were saved inside the container
- When the container restarted, all uploaded files were lost
- Result: **Blank/empty PDF** because the SVG template file didn't exist

### 2. **Wrong AFRP Logo File Extension** ❌
- Config was looking for: `afrp_logo.png`
- Actual file created: `afrp_logo.svg`
- Result: Logo wouldn't load

### 3. **Badge Folders Didn't Exist** ❌
- `badge_templates/` and `badge_logos/` folders weren't created on the host
- Result: Volume mounts would fail

---

## ✅ Fixes Applied

### 1. **Added Volume Mounts to docker-compose.yaml**
```yaml
volumes:
  - ./badge_templates:/app/badge_templates  # NEW
  - ./badge_logos:/app/badge_logos          # NEW
  - ./static:/app/static                    # NEW
```

Now uploaded templates persist across restarts!

### 2. **Fixed AFRP Logo Path**
```python
# Changed from:
app.config['AFRP_LOGO_PATH'] = os.path.join(BASE_PATH, 'static', 'afrp_logo.png')

# To:
app.config['AFRP_LOGO_PATH'] = os.path.join(BASE_PATH, 'static', 'afrp_logo.svg')
```

### 3. **Created Badge Folders**
```bash
mkdir -p badge_templates badge_logos
chmod -R 777 badge_templates badge_logos
```

### 4. **Added Extensive Logging**
Added detailed logging to `badge_generator.py` to help diagnose future issues:
- Shows Excel columns being read
- Shows column mappings being used
- Shows file paths and existence checks
- Shows each step of SVG rendering
- Shows QR code generation status
- Shows image encoding status

---

## 🚀 What You Need to Do Now

### Step 1: Re-upload Your Badge Template

Since the previous upload was lost (not persisted), you need to upload it again:

1. **Go to**: http://localhost:5066/badge-mapping

2. **Upload SVG Template**:
   - Choose one from `/static/svg/`:
     - `minimal_badge_template.svg` (simple, recommended for first test)
     - `sample_badge_template.svg` (full-featured)
     - `formal_badge_template.svg` (professional)
   - Click "Choose SVG File" or drag-and-drop
   - System will extract placeholders automatically

3. **Map Columns** (for minimal template):
   - `{{FIRST_NAME}}` → "First Name"
   - `{{LAST_NAME}}` → "Last Name"
   - `{{MEMBER_ID}}` → "Member ID"
   - `{{LOCAL_CLUB}}` → "Local Club"
   - `{{QR_CODE}}` → "QR Code"
   - `{{AFRP_LOGO}}` → (leave as default)
   - `{{CLUB_LOGO}}` → (leave empty or upload logo)

4. **Select Avery Template**: 5392 (3" × 4")

5. **Save Template**: Name it "Test Badge" or something descriptive

6. **Verify Upload**: Check that file exists:
   ```bash
   ls -la /home/rumz/git/qr_code_generator/badge_templates/
   ```
   You should see your SVG file there now!

### Step 2: Generate Test Badges

1. **Go to**: http://localhost:5066/badges-v2

2. **Select**:
   - Campaign: Pick a small test campaign (5-10 people)
   - Badge Template: "Test Badge" (or whatever you named it)
   - Avery Template: 5392

3. **Click**: "Pull, Process & Generate Badges"

4. **Wait**: System will:
   - Pull data from CRM
   - Process it
   - Generate QR codes
   - Render SVG badges
   - Create PDF with Avery layout
   - Download automatically

5. **Open PDF**: You should now see actual badges with:
   - Names
   - Member IDs
   - Club names
   - QR codes
   - AFRP logo
   - All properly arranged on 3"×4" badges

### Step 3: Verify Output

1. **Open the PDF**
2. **Check first page**:
   - Should have 8 badges (2×4 layout for Avery 5392)
   - Each badge should have data (not blank!)
   - Text should be readable
   - QR codes should be visible
   - AFRP logo should appear

3. **Test QR Code**:
   - Use phone camera or QR scanner app
   - Scan one of the QR codes
   - Should decode to the QR code string from CRM

---

## 🔍 Debugging (If Still Having Issues)

### View Detailed Logs

```bash
# See full logs
docker-compose logs --tail=100 afrp-helper

# Filter for badge generation
docker-compose logs afrp-helper | grep badge_generator

# See errors only
docker-compose logs afrp-helper | grep ERROR
```

### Common Issues and Solutions

#### "Template not found" error
**Problem**: SVG file wasn't uploaded or doesn't exist
**Solution**: 
```bash
# Check if file exists
ls -la /home/rumz/git/qr_code_generator/badge_templates/

# If empty, re-upload through UI
# File should appear in this folder after upload
```

#### "AFRP logo not found" warning
**Problem**: Logo file doesn't exist or wrong path
**Solution**:
```bash
# Check logo exists
ls -la /home/rumz/git/qr_code_generator/static/afrp_logo.svg

# If missing, it was created in static/svg/ - copy it:
cp static/svg/afrp_logo.svg static/
```

#### PDF still blank
**Check the logs**:
```bash
docker-compose logs afrp-helper | tail -200 | grep -E "(badge_generator|ERROR|WARNING)"
```

Look for:
- "Failed to convert SVG to drawing" - SVG is malformed
- "Column '...' not found" - Column mapping is wrong
- "QR Code data is empty" - No QR code data in Excel

#### Badges not aligned on sheet
**Problem**: Wrong Avery template selected
**Solution**: 
- Verify your physical Avery label sheets match the template code
- 5392 is 3" × 4", 8 per sheet (most common)
- Print ONE test sheet first before bulk printing

---

## 📊 System Status

### What's Now Working:
- ✅ AFRP logo path fixed (points to .svg)
- ✅ Docker volume mounts added (templates persist)
- ✅ Badge folders created and mounted
- ✅ Static folder mounted for logos
- ✅ Extensive logging added for debugging
- ✅ Badge generation UI integrated
- ✅ Template configuration UI working
- ✅ Database for template storage
- ✅ All API endpoints functional

### What You Need to Complete:
- ⏳ Re-upload your badge template (lost in previous container)
- ⏳ Map columns to placeholders
- ⏳ Generate first test PDF
- ⏳ Verify badges print correctly

---

## 🎓 Key Learnings

### Why This Happened
1. Docker containers are **ephemeral** - data inside them doesn't persist
2. **Volume mounts** are required to save data between restarts
3. Initial setup didn't include badge storage volumes
4. File uploads went to container, not host filesystem

### What's Different Now
- Badge templates → saved to `/home/rumz/git/qr_code_generator/badge_templates/`
- Badge logos → saved to `/home/rumz/git/qr_code_generator/badge_logos/`
- Static files → accessible at `/home/rumz/git/qr_code_generator/static/`
- All changes persist across restarts ✅

---

## 📞 Next Steps Summary

1. ✅ **Fixed** - Logo path, volume mounts, logging
2. ⏳ **Your Turn** - Re-upload template via UI
3. ⏳ **Test** - Generate badges for small campaign
4. ⏳ **Verify** - Check PDF has actual badge data
5. ⏳ **Print** - Print one test sheet on Avery labels
6. ⏳ **Scan** - Test QR codes with phone
7. ⏳ **Scale** - Generate badges for full event!

---

## 🎯 Expected Result

After completing the steps above, you should get a PDF like this:

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  [AFRP]  JOHN SMITH  [Club]    [AFRP]  JANE DOE │
│           ID-00094                     ID-00095  │
│     San Francisco Chapter        Boston Chapter  │
│           [QR]                          [QR]     │
│                                                  │
│  [AFRP]  BOB JONES   [Club]    [AFRP]  SUE LEE  │
│           ID-00096                     ID-00097  │
│      Chicago Chapter             NYC Chapter     │
│           [QR]                          [QR]     │
│                                                  │
│  ... 4 more badges ...                          │
│                                                  │
└──────────────────────────────────────────────────┘
          Page 1 of N (8 badges per page)
```

**No more blank pages!** 🎉

---

**Ready to test?** Go to http://localhost:5066/badge-mapping and upload your template!
