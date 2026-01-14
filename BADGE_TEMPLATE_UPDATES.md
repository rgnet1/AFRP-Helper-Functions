# Badge Template Updates - Table Number & Sub-Events

## ✅ What Was Added

### 1. **Banquet Table Number**
Added a table number field that displays below the Local Club name.

**Placeholder**: `{{TABLE_NUMBER}}`

**Example mapping**: Map to column like `Grand Banquet ~ Table` or `Convention 2025 ~ Table`

### 2. **Sub-Events Listing (Bottom Left)**
Added support for displaying up to 3 sub-events the attendee registered for.

**Placeholders**:
- `{{SUBEVENT_1}}`
- `{{SUBEVENT_2}}`
- `{{SUBEVENT_3}}`

**Multi-select support**: Each sub-event placeholder can be mapped to multiple Excel columns!

---

## 🎨 Updated Layout (Landscape Badge)

```
┌────────────────────────────────────────────┐
│  [AFRP Logo]              [Club Logo]      │
│                                            │
│         FIRST NAME LAST NAME               │ ← One line, centered
│                                            │
│           Local Club Name                  │ ← Centered
│             Table 5                        │ ← NEW: Table number
│                                            │
│ EVENTS:                      ID-00094      │
│ Grand Banquet                  [QR]        │ ← Sub-events (left)
│ Ahla w Sahla Night                         │    QR code (right)
│ Keynote Speech                             │
└────────────────────────────────────────────┘
```

---

## 🔧 Features Added

### **Multi-Select for Sub-Events**
In the badge mapping UI (`/badge-mapping`), when you map sub-event placeholders:

1. **Multi-select dropdown** appears for `{{SUBEVENT_1}}`, `{{SUBEVENT_2}}`, `{{SUBEVENT_3}}`
2. **Hold Ctrl/Cmd** to select multiple event columns
3. **System automatically combines** the selected events

**Example**:
- Select: `Grand Banquet`, `Ahla w Sahla Night`, `Keynote Speech` for `{{SUBEVENT_1}}`
- Badge will show all events the person is registered for

### **More Column Options**
Added these columns to the mapping dropdown:
- `Contact ID`
- `Grand Banquet`
- `Ahla w Sahla Night`
- `Mid-Year Meeting 2026 - Lexington`
- `Grand Banquet ~ Table`
- `Convention 2025 ~ Table`
- `Sub-Event 1`, `Sub-Event 2`, `Sub-Event 3`

---

## 📝 How to Use

### **Mapping the Table Number**

1. Go to `/badge-mapping`
2. Upload your SVG template (with `{{TABLE_NUMBER}}`)
3. For the `{{TABLE_NUMBER}}` placeholder:
   - Map to a column like: `Grand Banquet ~ Table`
   - Or whichever event has table assignments
4. Save template

**Result**: Badge will show "Table 5" (or whatever table number)

---

### **Mapping Sub-Events**

1. In `/badge-mapping`, find the `{{SUBEVENT_1}}` placeholder
2. You'll see a **multi-select dropdown** (taller than normal)
3. **Hold Ctrl (Windows) or Cmd (Mac)**
4. Click to select multiple event columns:
   - `Grand Banquet`
   - `Ahla w Sahla Night`
   - `Mid-Year Meeting 2026 - Lexington`
   - Any other event columns
5. Repeat for `{{SUBEVENT_2}}` and `{{SUBEVENT_3}}` if needed
6. Save template

**Result**: Badge will list all events the person is registered for

---

## 🧪 Example Mapping Configuration

```
Placeholder Mappings:
├─ {{FIRST_NAME}} → First Name
├─ {{LAST_NAME}} → Last Name
├─ {{LOCAL_CLUB}} → Local Club
├─ {{MEMBER_ID}} → Member ID
├─ {{TABLE_NUMBER}} → Grand Banquet ~ Table
├─ {{QR_CODE}} → QR Code
├─ {{SUBEVENT_1}} → [Grand Banquet, Ahla w Sahla Night, Keynote]
├─ {{SUBEVENT_2}} → [Workshop A, Workshop B]
└─ {{SUBEVENT_3}} → [Dinner Dance]
```

---

## 💡 Smart Sub-Event Handling

The system **intelligently handles** sub-events:

### **Scenario 1**: Person registered for 3 events
- `{{SUBEVENT_1}}` maps to: Grand Banquet, Ahla w Sahla Night, Keynote
- **Badge shows**: All 3 events that person is registered for
- If person only registered for Grand Banquet, only that appears

### **Scenario 2**: Person registered for 5+ events
- `{{SUBEVENT_1}}` maps to first 3 events
- `{{SUBEVENT_2}}` maps to next 2 events
- Badge shows all events across both placeholders

### **Scenario 3**: Person not registered for any events
- Placeholder stays **empty** (no text shown)
- Badge still looks clean

---

## 🎯 Column Name Patterns

Your Excel output contains columns like:
- **Simple event columns**: `Grand Banquet`, `Ahla w Sahla Night`
- **Table columns**: `Grand Banquet ~ Table`, `Convention 2025 ~ Table`
- **Form responses**: Various question/response columns

**For sub-events**: Select the event name columns (without "~ Table")

**For table numbers**: Select the column with "~ Table"

---

## 📋 Updated Files

### SVG Templates:
- ✅ `static/svg/minimal_badge_landscape.svg` (source)
- ✅ `badge_templates/minimal_badge_landscape.svg` (used by system)

### UI Code:
- ✅ `templates/badge_mapping.html`:
  - Added table and sub-event columns to dropdown
  - Multi-select UI for sub-events
  - Updated `getMappings()` to handle arrays
  - Updated `renderMappingInterface()` to show multi-select

### Backend:
- ✅ Already supports list mappings (no changes needed!)

---

## 🔍 How Multi-Select Works

### In the UI:
1. **Detect sub-event placeholders** (contains "SUBEVENT")
2. **Render multi-select** dropdown (height: 80px)
3. **User holds Ctrl/Cmd** and clicks multiple options
4. **Save as array**: `{'{{SUBEVENT_1}}': ['Event A', 'Event B']}`

### In the Backend:
1. **Checks if mapping is array** (`isinstance(column_name, list)`)
2. **Loops through each column** in the array
3. **Checks if person is registered** (column has value)
4. **Collects event names** and joins with newlines
5. **Replaces placeholder** with the list

**Result**: Badge shows all relevant events!

---

## ✅ Status

- **Container rebuilt** with all changes
- **Templates updated** with table and sub-events
- **UI enhanced** with multi-select capability
- **Ready to use!**

---

## 🚀 Next Steps

1. **Go to**: http://localhost:5066/badge-mapping
2. **Upload** the updated `minimal_badge_landscape.svg`
3. **Map placeholders**:
   - Regular fields: Single-select dropdown
   - Sub-events: Multi-select dropdown (hold Ctrl/Cmd)
4. **Save template**
5. **Generate badges** - table numbers and events will appear!

---

## 💡 Pro Tips

### Tip 1: Smart Event Selection
If you have 10 events but only want to show 3 most important ones on badges:
- Map `{{SUBEVENT_1}}` to only those 3 event columns
- Saves space, highlights key events

### Tip 2: Table Numbers
Different events may have different table columns:
- `Grand Banquet ~ Table`
- `Gala Dinner ~ Table`
- Map to the one relevant for your event

### Tip 3: Empty Placeholders
If someone isn't registered for events, or doesn't have a table:
- Placeholder shows nothing
- Badge still looks professional

### Tip 4: Testing
Generate badges for 2-3 people with different registrations:
- Person with all events
- Person with 1 event
- Person with no events
Verify layout looks good in all cases!

---

**All features implemented and ready to use!** 🎉
