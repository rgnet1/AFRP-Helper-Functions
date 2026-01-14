# SVG Badge Templates

This folder contains sample SVG badge templates that you can use and customize for your events.

## 📋 Available Templates

### 1. `sample_badge_template.svg` (Full-Featured)
A comprehensive badge template with all available fields:
- AFRP and Club logos
- Title, Name, Member ID
- Local Club affiliation
- Gender and Age (optional)
- Up to 3 sub-events
- QR code with label
- Decorative border and header band

**Best for**: Large events where you need to display multiple pieces of information.

### 2. `minimal_badge_template.svg` (Simple & Clean)
A minimalist badge with just the essentials:
- AFRP and Club logos
- First and Last Name (large)
- Member ID
- Local Club
- QR code

**Best for**: Events where you want a clean, uncluttered look.

---

## 🎨 How to Customize

### Using a Text Editor (Quick Edits)

1. Open the SVG file in any text editor
2. Find the element you want to modify
3. Change attributes like `font-size`, `fill` (color), `x`, `y` (position)
4. Save and upload to `/badge-mapping`

**Example - Make name bigger:**
```xml
<!-- Change from font-size="22" to font-size="32" -->
<text x="144" y="115" 
      font-size="32"   ← Change this number
      font-weight="bold">{{FIRST_NAME}}</text>
```

**Example - Change color:**
```xml
<!-- Change from green to blue -->
<text fill="#0000ff">{{LOCAL_CLUB}}</text>
       ↑ Blue in hex
```

### Using Inkscape or Illustrator (Visual Editing)

1. **Open** the SVG in Inkscape (free) or Adobe Illustrator
2. **Edit** text, shapes, colors visually
3. **Keep placeholders**: Don't delete text like `{{FIRST_NAME}}`
4. **Save As** → Plain SVG (Inkscape) or SVG (Illustrator)
5. **Upload** to your badge system

---

## 🔤 Available Placeholders

These placeholders get replaced with actual attendee data:

| Placeholder | Description | Example |
|------------|-------------|---------|
| `{{FIRST_NAME}}` | First name | John |
| `{{LAST_NAME}}` | Last name | Smith |
| `{{TITLE}}` | Title | Dr. |
| `{{MEMBER_ID}}` | Member ID | ID-00094 |
| `{{LOCAL_CLUB}}` | Club name | San Francisco Chapter |
| `{{GENDER}}` | Gender | Male / Female |
| `{{AGE}}` | Age in years | 42 |
| `{{QR_CODE}}` | QR code image | *(auto-generated)* |
| `{{AFRP_LOGO}}` | Default AFRP logo | *(from system)* |
| `{{CLUB_LOGO}}` | Custom club logo | *(uploaded by you)* |
| `{{SUBEVENT_1}}` | 1st sub-event | Workshop A |
| `{{SUBEVENT_2}}` | 2nd sub-event | Dinner |
| `{{SUBEVENT_3}}` | 3rd sub-event | Keynote |

You can also use any column from your Excel output!

---

## 📐 Template Sizes (Avery Labels)

Your SVG should match the Avery template size you'll be printing on:

| Avery Code | Physical Size | SVG Size (96 DPI) | Layout |
|------------|---------------|-------------------|--------|
| **5392** | 3" × 4" | 288 × 384 px | 2×2 (8 per sheet) |
| 5395 | 2.625" × 3.625" | 252 × 348 px | 2×2 (8 per sheet) |
| 8395 | 2.625" × 3.625" | 252 × 348 px | 2×2 (8 per sheet) |
| 74459 | 2.25" × 3.5" | 216 × 336 px | 3×2 (12 per sheet) |

**Formula**: Inches × 96 = Pixels

The provided templates are sized for **Avery 5392** (most common).

---

## 🎯 Quick Customization Guide

### Change Font

```xml
<!-- Current -->
<text font-family="Arial">

<!-- Options -->
<text font-family="Helvetica">
<text font-family="Times New Roman">
<text font-family="Courier">
<text font-family="Verdana">
<text font-family="Georgia">
```

### Change Colors

```xml
<!-- Common Colors -->
<text fill="#000000">  <!-- Black -->
<text fill="#FFFFFF">  <!-- White -->
<text fill="#4b904b">  <!-- Green -->
<text fill="#0066cc">  <!-- Blue -->
<text fill="#cc0000">  <!-- Red -->
<text fill="#666666">  <!-- Gray -->
```

### Change Text Size

```xml
<text font-size="8">   <!-- Very small -->
<text font-size="12">  <!-- Small -->
<text font-size="16">  <!-- Medium -->
<text font-size="22">  <!-- Large -->
<text font-size="32">  <!-- Very large -->
```

### Move Elements

```xml
<!-- x = horizontal position (0 = left, 288 = right for Avery 5392) -->
<!-- y = vertical position (0 = top, 384 = bottom for Avery 5392) -->

<text x="144" y="100">  <!-- Centered horizontally, near top -->
<text x="20" y="100">   <!-- Left side -->
<text x="268" y="100">  <!-- Right side -->
```

### Resize Images/Logos

```xml
<image width="50" height="50">   <!-- Small logo -->
<image width="80" height="80">   <!-- Medium logo -->
<image width="120" height="120"> <!-- Large logo -->
```

### Add a Background Color

```xml
<!-- Add after the opening <svg> tag -->
<rect width="288" height="384" fill="#f0f0f0"/>
```

### Add a Header Banner

```xml
<rect x="0" y="0" width="288" height="80" fill="#4b904b"/>
<text x="144" y="50" 
      text-anchor="middle" 
      font-size="20" 
      fill="#FFFFFF">CONFERENCE 2025</text>
```

---

## 💡 Design Tips

### Do's ✅
- **Use web-safe fonts** (Arial, Helvetica, Times New Roman)
- **Leave 0.25" margin** from edges for printing safety
- **Use high contrast** (dark text on light background)
- **Make QR codes at least 0.75"** for reliable scanning
- **Test with 2-3 badges** before printing hundreds
- **Keep it simple** - less is more for readability

### Don'ts ❌
- **Avoid complex gradients** - may not render correctly
- **Don't use very small fonts** (< 8pt) - hard to read
- **Don't crowd elements** - leave breathing room
- **Don't rely on color alone** - ensure contrast
- **Don't place critical info near edges** - may get cut off

---

## 🔧 Creating Your Own Template

### From Scratch

1. **Set canvas size** to match Avery template (e.g., 288 × 384 px)
2. **Add logos** using `<image>` with `{{AFRP_LOGO}}` and `{{CLUB_LOGO}}`
3. **Add text fields** using `<text>` with placeholders like `{{FIRST_NAME}}`
4. **Add QR code** using `<image>` with `{{QR_CODE}}`
5. **Test layout** - upload and generate 1-2 sample badges
6. **Refine** - adjust positions, sizes, colors

### From Existing Template

1. **Copy** `sample_badge_template.svg` to a new file
2. **Rename** to describe your event (e.g., `convention_2025.svg`)
3. **Remove** sections you don't need (e.g., gender/age, sub-events)
4. **Adjust** remaining elements as needed
5. **Save** and upload

---

## 📁 File Organization

```
static/svg/
├── README.md                      ← You are here
├── sample_badge_template.svg      ← Full-featured template
├── minimal_badge_template.svg     ← Simple template
└── [your_custom_templates.svg]    ← Add your own here
```

**Tip**: Keep your custom templates in this folder for easy access and version control!

---

## 🚀 Next Steps

1. **Choose** a starting template (sample or minimal)
2. **Customize** it to match your event branding
3. **Upload** to http://localhost:5066/badge-mapping
4. **Map** columns to placeholders
5. **Save** the configuration
6. **Generate** test badges with 2-3 attendees
7. **Print** on Avery labels and verify
8. **Scale up** to full event!

---

## 🆘 Need Help?

- **SVG Basics**: https://developer.mozilla.org/en-US/docs/Web/SVG/Tutorial
- **Inkscape** (Free SVG Editor): https://inkscape.org/
- **Color Picker**: https://htmlcolorcodes.com/
- **Web-Safe Fonts**: https://www.w3schools.com/cssref/css_websafe_fonts.php

---

**Happy Badge Making! 🎉**
