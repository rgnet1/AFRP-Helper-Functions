# 📋 Badge Template Comparison

Quick reference to help you choose the right template for your event.

---

## 🎨 Available Templates

### 1. 📌 `minimal_badge_template.svg`

**Best For**: Simple events, clean look, easy to read

**What's Included**:
- ✅ AFRP Logo (top left)
- ✅ Club Logo (top right)
- ✅ First Name (large, bold)
- ✅ Last Name (large, bold)
- ✅ Member ID
- ✅ Local Club (in green)
- ✅ QR Code (bottom center)
- ✅ Simple border

**What's NOT Included**:
- ❌ Title (Mr./Mrs./Dr.)
- ❌ Gender/Age
- ❌ Sub-events
- ❌ Decorative elements

**Layout Preview**:
```
┌──────────────────────────────┐
│  [AFRP]           [Club]     │  ← Logos
│                              │
│                              │
│         JOHN                 │  ← First Name (28px, bold)
│         SMITH                │  ← Last Name (28px, bold)
│                              │
│        ID-00094              │  ← Member ID (16px)
│    San Francisco Chapter     │  ← Local Club (14px, green)
│                              │
│          [QR]                │  ← QR Code
└──────────────────────────────┘
```

**File Size**: ~1 KB  
**Complexity**: ⭐ Easy

---

### 2. 🎯 `sample_badge_template.svg`

**Best For**: Large events, maximum information display

**What's Included**:
- ✅ AFRP Logo (top left)
- ✅ Club Logo (top right)
- ✅ Title (Dr./Mr./Mrs.)
- ✅ First Name (22px, bold)
- ✅ Last Name (22px, bold)
- ✅ Member ID
- ✅ Local Club (in green)
- ✅ Gender and Age (optional, small)
- ✅ Sub-events section (up to 3 events)
- ✅ QR Code with label
- ✅ Decorative border
- ✅ Header band (light green)

**Layout Preview**:
```
┌──────────────────────────────┐
│  [AFRP]  [Header]  [Club]    │  ← Logos + decorative header
│                              │
│           Dr.                │  ← Title (12px)
│          JOHN                │  ← First Name (22px, bold)
│          SMITH               │  ← Last Name (22px, bold)
│        ID-00094              │  ← Member ID (14px)
│    San Francisco Chapter     │  ← Local Club (13px, green)
│      Male • 42 years old     │  ← Gender/Age (10px, gray)
│ ─────────────────────────── │  ← Divider
│     REGISTERED EVENTS        │  ← Section header
│        Workshop A            │  ← Sub-event 1
│        Gala Dinner           │  ← Sub-event 2
│      Keynote Speech          │  ← Sub-event 3
│                              │
│          [QR]                │  ← QR Code
│      Scan for Details        │  ← Label (8px)
└──────────────────────────────┘
```

**File Size**: ~3 KB  
**Complexity**: ⭐⭐⭐ Advanced

---

### 3. 👔 `formal_badge_template.svg`

**Best For**: Professional conferences, formal events, elegant look

**What's Included**:
- ✅ AFRP Logo (small, top left)
- ✅ Club Logo (small, top right)
- ✅ Title (italic, subtle)
- ✅ First Name (26px, serif font, bold)
- ✅ Last Name (26px, serif font, bold, uppercase)
- ✅ Member ID (prominent, green)
- ✅ Local Club
- ✅ QR Code (larger for easy scanning)
- ✅ Gold accent lines (decorative)
- ✅ Top and bottom border accents

**Special Features**:
- Serif fonts (Georgia) for elegance
- Gold accent color (#d4af37)
- Uppercase last names for formality
- Larger QR code (70px vs 60px)
- Professional color palette

**Layout Preview**:
```
┌──────────────────────────────┐
│ ████████████████████████████ │  ← Green/gold top accent
│  [L]                   [L]   │  ← Small logos
│ ─────────────────────────── │  ← Divider
│                              │
│           Dr.                │  ← Title (11px, italic, gray)
│                              │
│          JOHN                │  ← First Name (26px, serif, bold)
│          SMITH               │  ← Last Name (26px, serif, CAPS)
│      ─────────────           │  ← Gold decorative line
│                              │
│        ID-00094              │  ← Member ID (15px, green, bold)
│    San Francisco Chapter     │  ← Local Club (13px)
│ ─────────────────────────── │  ← Divider
│                              │
│          [QR]                │  ← Larger QR Code (70px)
│                              │
│ ████████████████████████████ │  ← Green/gold bottom accent
└──────────────────────────────┘
```

**File Size**: ~2 KB  
**Complexity**: ⭐⭐ Moderate

---

## 🔍 Quick Comparison Table

| Feature | Minimal | Sample | Formal |
|---------|---------|--------|--------|
| **Best For** | Simple events | Info-heavy | Professional |
| **Name Size** | 28px | 22px | 26px |
| **Font Style** | Sans-serif | Sans-serif | Serif |
| **Title Field** | ❌ | ✅ | ✅ (italic) |
| **Gender/Age** | ❌ | ✅ | ❌ |
| **Sub-Events** | ❌ | ✅ (3 max) | ❌ |
| **QR Code Size** | 60px | 60px | 70px |
| **Decorations** | Basic border | Header band | Gold accents |
| **Color Scheme** | Simple | Green theme | Green + Gold |
| **Logo Size** | 60px | 50px | 40px |
| **Readability** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Elegance** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Info Density** | Low | High | Medium |

---

## 🎯 Use Case Recommendations

### Choose **MINIMAL** if:
- ✅ First-time badge creation
- ✅ Want maximum readability
- ✅ Don't need sub-event info
- ✅ Want fastest printing
- ✅ Prefer simplicity

**Example Events**:
- Local club meetings
- Small workshops
- Casual gatherings
- Testing/debugging

---

### Choose **SAMPLE** if:
- ✅ Multi-day conference with multiple sessions
- ✅ Need to show which events people registered for
- ✅ Want all information on one badge
- ✅ Attendees need to see gender/age info
- ✅ Complex event structure

**Example Events**:
- Annual conventions
- Multi-track conferences
- Events with breakout sessions
- Registration with meal/activity choices

---

### Choose **FORMAL** if:
- ✅ Professional/corporate event
- ✅ Want elegant, sophisticated look
- ✅ Audience expects formal presentation
- ✅ Need larger QR code for networking
- ✅ Brand image is important

**Example Events**:
- Board meetings
- Professional conferences
- Gala dinners
- Executive retreats
- High-profile events

---

## 🛠️ Customization Difficulty

### Easy Customizations (All Templates)
- Change colors (`fill="#hexcode"`)
- Change font sizes (`font-size="24"`)
- Move elements up/down (adjust `y` values)
- Show/hide optional fields (delete or comment out)

### Moderate Customizations
- Add new text fields
- Resize logos
- Change fonts
- Add simple shapes (rectangles, circles)

### Advanced Customizations
- Add gradients
- Create custom decorative elements
- Complex layouts
- Multiple columns
- Background images

---

## 💡 Mixing and Matching

You can combine features from different templates:

**Example 1**: Minimal + Sub-Events
- Start with `minimal_badge_template.svg`
- Copy sub-events section from `sample_badge_template.svg`
- Adjust vertical positions

**Example 2**: Formal + Gender/Age
- Start with `formal_badge_template.svg`
- Copy gender/age line from `sample_badge_template.svg`
- Match font styles and colors

**Example 3**: Sample + Formal Colors
- Start with `sample_badge_template.svg`
- Change colors to match `formal_badge_template.svg`
- Add gold accent lines

---

## 📏 Size Guidelines

All templates are designed for **Avery 5392** (3" × 4" = 288 × 384 pixels):

### Element Sizing Recommendations

| Element | Recommended Size | Minimum Size |
|---------|------------------|--------------|
| Name Text | 22-32px | 18px |
| Member ID | 14-16px | 12px |
| Club/Details | 12-14px | 10px |
| Small Text | 8-10px | 8px |
| Logos | 40-60px | 30px |
| QR Code | 60-70px | 55px |
| Margins | 24px (0.25") | 15px |

---

## 🎨 Color Palette Reference

### Primary Colors (Used in Templates)

| Color | Hex Code | Usage |
|-------|----------|-------|
| **AFRP Green** | `#4b904b` | Logos, accents, club names |
| **Dark Green** | `#3c723c` | Borders, secondary |
| **Gold** | `#d4af37` | Formal accents (formal template) |
| **Black** | `#000000` | Main text |
| **Dark Gray** | `#333333` | Secondary text |
| **Medium Gray** | `#666666` | Tertiary text |
| **Light Gray** | `#999999` | Optional/subtle text |
| **White** | `#FFFFFF` | Background |

---

## 📝 Next Steps

1. **Review** the comparison above
2. **Choose** a template that matches your event
3. **Test** by generating 2-3 sample badges
4. **Customize** if needed (colors, sizes, layout)
5. **Save** your configuration
6. **Generate** badges for your event!

---

## 🔄 Template Evolution

Start simple, evolve as needed:

```
Event 1: Minimal template
   ↓ (works great, but need sub-events)
Event 2: Sample template
   ↓ (too much info, want elegant look)
Event 3: Formal template
   ↓ (perfect! but want to add one field)
Event 4: Custom template (based on formal)
```

**Pro Tip**: Keep all versions! You'll reuse them for different event types.

---

**Ready to create badges?** Pick a template and go to:
- **Configure**: http://localhost:5066/badge-mapping
- **Generate**: http://localhost:5066/badges-v2

**Happy Badge Making! 🎉**
