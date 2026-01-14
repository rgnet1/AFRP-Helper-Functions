# 🚀 Quick Start: Creating Your First Badge

Follow these steps to generate your first batch of badges in under 10 minutes!

---

## ✅ What You Have Now

Your system now includes:

1. ✅ **2 Sample SVG Templates**:
   - `sample_badge_template.svg` - Full-featured with all fields
   - `minimal_badge_template.svg` - Simple and clean

2. ✅ **Placeholder AFRP Logo**:
   - `static/afrp_logo.svg` - Green circle with "AFRP LOGO"
   - Replace with your actual logo (PNG, JPG, or SVG)

3. ✅ **Complete Badge System**:
   - Template configuration UI
   - Badge generation engine
   - PDF export with Avery layouts

---

## 📝 5-Minute Setup

### Step 1: Replace the AFRP Logo (Optional)

```bash
# Replace the placeholder logo with your actual logo
# File: static/afrp_logo.svg (or .png)
```

Or use the placeholder for now and skip this step.

### Step 2: Upload Your First Template

1. **Open**: http://localhost:5066/badge-mapping
2. **Upload SVG**: 
   - Click "Choose SVG File" or drag-and-drop
   - Select: `static/svg/minimal_badge_template.svg`
   - System auto-detects placeholders
3. **See**: List of placeholders like `{{FIRST_NAME}}`, `{{LAST_NAME}}`, etc.

### Step 3: Map Your Columns

For each placeholder, select the matching Excel column:

| Placeholder | Map To Excel Column |
|------------|---------------------|
| `{{FIRST_NAME}}` | → First Name |
| `{{LAST_NAME}}` | → Last Name |
| `{{MEMBER_ID}}` | → Member ID |
| `{{LOCAL_CLUB}}` | → Local Club |
| `{{QR_CODE}}` | → QR Code |
| `{{AFRP_LOGO}}` | → *(leave as default)* |
| `{{CLUB_LOGO}}` | → *(upload image or skip)* |

### Step 4: Select Avery Template

- Choose: **5392 - Name Badge Insert Refills (3" × 4")**
- This is the most common size

### Step 5: Save Your Template

- **Template Name**: "My First Badge"
- Click: **"Save Template"**
- Done! ✅

---

## 🎯 Generate Your First Badges

### Method 1: Process Then Generate (Recommended for First Time)

1. **Go to**: http://localhost:5066/badges-v2

2. **Select Campaign**:
   - Choose a small test campaign (5-10 people)

3. **Click**: "Pull All & Process"
   - Wait for Excel file to download
   - Open it to verify data looks correct

4. **Scroll to Badge Generation Section**

5. **Select**:
   - Badge Template: "My First Badge"
   - Avery Template: 5392 (should be pre-selected)

6. **Click**: "Generate Badges from Processed Data"

7. **Wait**: Progress bar shows generation status

8. **Download**: PDF automatically downloads

9. **Open PDF**: Verify badges look correct

### Method 2: One-Click (After You're Comfortable)

1. **Go to**: http://localhost:5066/badges-v2

2. **Select**:
   - Campaign
   - Badge Template
   - Avery Template

3. **Click**: "Pull, Process & Generate Badges"

4. **Wait**: System does everything automatically

5. **Download**: PDF with badges ready to print!

---

## 🖨️ Printing Your Badges

### What You Need

1. **Avery Label Sheets**: 
   - Avery 5392 (or whichever template you selected)
   - Available at office supply stores
   - 8 badges per sheet

2. **Printer**:
   - Regular inkjet or laser printer
   - Color recommended (for logos and styling)

### How to Print

1. **Open** the downloaded PDF
2. **Print Settings**:
   - Paper size: Letter (8.5" × 11")
   - Scale: 100% (Do NOT scale to fit)
   - Margins: None
   - Print quality: High
3. **Load** Avery sheets in printer
4. **Print** a test page first!
5. **Verify alignment** with Avery template
6. **Print remaining** sheets

### Troubleshooting Print Alignment

- **Badges too high/low**: Adjust top margin in printer settings
- **Badges too left/right**: Adjust side margins
- **Badges too small/large**: Ensure 100% scale (no shrink-to-fit)

---

## 🎨 Customizing Your Badge Design

### Easy Text Changes (No Design Software)

Edit SVG in any text editor:

```xml
<!-- Make name bigger -->
<text font-size="32">{{FIRST_NAME}}</text>  ← Change 32 to a bigger number

<!-- Change color to blue -->
<text fill="#0000ff">{{LOCAL_CLUB}}</text>  ← #0000ff is blue

<!-- Move element down -->
<text y="150">{{MEMBER_ID}}</text>          ← Increase y to move down
```

### Visual Editing (Recommended)

1. **Download Inkscape** (free): https://inkscape.org
2. **Open**: Your SVG template
3. **Edit**: Move, resize, change colors visually
4. **Keep**: All `{{PLACEHOLDER}}` text intact!
5. **Save As**: Plain SVG
6. **Re-upload**: to `/badge-mapping`

---

## 🔍 Testing Checklist

Before printing 500 badges, test with a small batch:

- [ ] Generate badges for 2-3 attendees
- [ ] Print on ONE Avery sheet
- [ ] Check alignment with Avery template
- [ ] Verify all text is readable
- [ ] Test QR code scanning with phone
- [ ] Check logo quality
- [ ] Verify member IDs are correct
- [ ] Ensure local club names fit
- [ ] Look for any text overflow

If everything looks good → Scale up! 🎉

---

## 📊 Column Reference

Your processed Excel file includes these columns (all available for badges):

### Core Fields
- First Name
- Last Name
- Title (Mr., Mrs., Dr., etc.)
- Member ID (ID-####)
- Local Club
- Gender
- Age

### Event Fields
- Event Name
- Registration Date
- Status

### Optional Fields
- QR Code (string - converted to image automatically)
- Table Reservations
- Form Responses
- Sub-Events

### Use ANY Column

You can add placeholders for any column in your Excel file:
- `{{COLUMN_NAME}}` - Just match the exact column name from Excel
- System will fill it in automatically

---

## 💡 Pro Tips

### Tip 1: Start Simple
Use `minimal_badge_template.svg` for your first event. Add complexity later.

### Tip 2: Print Test Sheets
Always print 1-2 test sheets before committing to hundreds.

### Tip 3: QR Code Size
Make QR codes at least 0.75" × 0.75" (72px × 72px) for reliable scanning.

### Tip 4: Font Sizes
- Names: 22-32px (large, bold)
- Member ID / Club: 12-16px (medium)
- Optional info: 8-10px (small)

### Tip 5: Margins
Leave 0.25" (24px) margin from badge edges for safe printing.

### Tip 6: Test QR Codes
After printing, scan QR codes with your phone to verify they work.

### Tip 7: Save Templates
Create one template per event type. Reuse for future events!

---

## 🆘 Common Issues

### "No templates found"
- Make sure you saved your template in `/badge-mapping`
- Refresh the page

### "Generate Badges" button disabled
- Select a template first
- For "from processed data": Run "Pull & Process" first

### QR codes don't scan
- Increase QR code size in SVG (minimum 72px × 72px)
- Ensure high print quality
- Check for smudging or ink issues

### Text is cut off
- Reduce font size
- Shorten text (e.g., abbreviate club names)
- Increase badge size or use different Avery template

### Logos don't show
- Verify `static/afrp_logo.svg` exists
- Upload club logo in `/badge-mapping` if using `{{CLUB_LOGO}}`
- Check file paths are correct

### Alignment is off when printing
- Print at 100% scale (no fit-to-page)
- Use correct Avery product number
- Adjust printer margins

---

## 📚 Additional Resources

- **Full User Guide**: `BADGE_GENERATION_USER_GUIDE.md`
- **SVG Customization**: `static/svg/README.md`
- **Sample Templates**: `static/svg/` folder
- **System Documentation**: Main project README

---

## ✨ You're Ready!

You now have everything you need to:
1. ✅ Configure badge templates
2. ✅ Pull attendee data from CRM
3. ✅ Generate QR codes
4. ✅ Create print-ready PDF badges
5. ✅ Print on Avery label sheets

**Next Step**: Go to http://localhost:5066/badges-v2 and generate your first badges!

---

**Questions?** Check the main `BADGE_GENERATION_USER_GUIDE.md` for detailed documentation.

**Happy Badge Making! 🎉**
