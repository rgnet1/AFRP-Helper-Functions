# Quick Fix Steps - Badge Generation

## ✅ What I Just Fixed

I copied all sample SVG templates to your `badge_templates` folder:
- `minimal_badge_template.svg` ✅
- `formal_badge_template.svg` ✅  
- `sample_badge_template.svg` ✅

The files are now at: `/home/rumz/git/qr_code_generator/badge_templates/`

---

## 🚀 Next: Configure Your Template (2 minutes)

You need to create a template **configuration** in the database that links to the SVG file.

### Step 1: Go to Template Configuration Page
**URL**: http://localhost:5066/badge-mapping

### Step 2: Upload/Select SVG Template

**Option A: Upload the file again** (recommended - creates proper database entry)
1. Click "Choose SVG File"
2. Navigate to: `/home/rumz/git/qr_code_generator/badge_templates/`
3. Select: `minimal_badge_template.svg` (start with simplest)
4. System will extract placeholders

**Option B: Manual configuration** (if upload works)
- The system should detect the file is already in badge_templates/

### Step 3: Map Your Columns

For `minimal_badge_template.svg`, map these:

| Placeholder | Map To Excel Column |
|------------|---------------------|
| `{{FIRST_NAME}}` | First Name |
| `{{LAST_NAME}}` | Last Name |
| `{{MEMBER_ID}}` | Member ID |
| `{{LOCAL_CLUB}}` | Local Club |
| `{{QR_CODE}}` | QR Code |
| `{{AFRP_LOGO}}` | *(leave as default)* |
| `{{CLUB_LOGO}}` | *(leave empty for now)* |

### Step 4: Select Avery Template
- Choose: **5392 - Name Badge Insert Refills (3" × 4")**

### Step 5: Save Template
- Template Name: **"Test Badge"** (or any name you want)
- Click: **"Save Template"**

---

## 🎯 Generate Badges

### Step 1: Go to Badge Generator
**URL**: http://localhost:5066/badges-v2

### Step 2: Select Options
1. **Campaign**: Choose a small test campaign (5-10 people)
2. Scroll down to "Badge Generation" section
3. **Badge Template**: Select "Test Badge" (or whatever you named it)
4. **Avery Template**: Should show 5392

### Step 3: Generate
Click: **"Pull, Process & Generate Badges"**

### Step 4: Verify
- PDF should download automatically
- Open it and check for actual badge data
- Should see names, IDs, QR codes, logos

---

## 🔍 If Still Having Issues

### Check Template Files Exist
```bash
ls -la /home/rumz/git/qr_code_generator/badge_templates/
```
Should show:
- formal_badge_template.svg
- minimal_badge_template.svg  
- sample_badge_template.svg

### Check Container Can See Files
```bash
docker-compose restart
docker-compose logs --tail=10 afrp-helper
```

### View Real-Time Logs
```bash
docker-compose logs -f afrp-helper
```

Then generate badges and watch logs for errors.

---

## 💡 Why This Happened

1. **You uploaded a template** through the UI → Created database record
2. **File went to container** (not host) → Lost on restart  
3. **Volume mount was added** → Now files persist
4. **Files were missing** → I copied them for you
5. **Database record incomplete** → Need to reconfigure through UI

---

## ✅ Summary

**What's Now Available:**
- ✅ All sample SVG files in `badge_templates/`
- ✅ Volume mounts working correctly
- ✅ Files persist across restarts

**What You Need to Do:**
1. ⏳ Go to http://localhost:5066/badge-mapping
2. ⏳ Upload/configure template (creates database entry)
3. ⏳ Map columns to placeholders
4. ⏳ Save configuration
5. ⏳ Generate badges!

**Expected Result:**
- PDF with actual badges (not blank)
- 8 badges per page (Avery 5392)
- Names, IDs, QR codes visible
- Ready to print! 🎉

---

**Ready?** Go to http://localhost:5066/badge-mapping and configure your template!
