# Event Preprocessing Classes (DEPRECATED)

## ⚠️ Important Notice

**These Python classes are DEPRECATED and no longer used by the system.**

The application now uses a **database-driven preprocessing system** where users can create and manage preprocessing templates through the web UI.

## Why These Files Still Exist

These files are kept as **reference examples only** to help understand the structure and logic of preprocessing transformations when creating new database templates.

## Current System

### Use the Preprocessing Designer UI

Instead of editing Python code, users can now:

1. Navigate to `/preprocessing-designer` in the application
2. Create preprocessing templates with a visual interface
3. Define value mappings (exact replacements)
4. Define contains mappings (substring removals)
5. Save templates to the database
6. Apply templates to any event without code changes

### Benefits of Database-Driven System

- ✅ No code changes required
- ✅ No container rebuild needed
- ✅ Instant updates and testing
- ✅ User-friendly visual interface
- ✅ Reusable across multiple events
- ✅ Version tracking with timestamps

## Reference Files

### default.py
Empty preprocessing template - no transformations applied. This is the fallback when no custom preprocessing is selected.

**Use case**: When you want data to flow through unchanged.

### convention2025.py
Example preprocessing for Convention 2025 event with:
- Value mappings for meal preferences
- Contains mappings for cleaning up text

**Use case**: Reference when creating templates for convention-style events.

### lex2026.py
Example preprocessing for Lex2026 convention with:
- Extensive value mappings
- Contains mappings for club name cleanup

**Use case**: Reference when creating templates for specific location-based events.

## How to Create New Preprocessing Templates

### Step 1: Go to Preprocessing Designer
Navigate to `http://your-domain/preprocessing-designer`

### Step 2: Create New Template
Click "New Template" and enter:
- **Name**: Descriptive name (e.g., "Detroit 2026")
- **Description**: What the template does

### Step 3: Add Value Mappings
For exact text replacements:
```
"Steak" → "S"
"Chicken" → "C"
"Vegetarian" → "V"
```

### Step 4: Add Contains Mappings
For substring removal:
```
"- Reserved" → ""
"Ramallah Federation in " → ""
```

### Step 5: Save Template
Click "Save Template" - it's immediately available for use!

### Step 6: Apply to Events
1. Go to Badge Generator (`/badges`)
2. Select your campaign
3. Choose your preprocessing template from dropdown
4. Click "Pull All & Process"

## Converting Legacy Classes to Database Templates

If you want to replicate one of these Python classes as a database template:

1. Open the Python file (e.g., `lex2026.py`)
2. Look at the `get_value_mappings()` method
3. Copy the dictionary contents
4. In Preprocessing Designer, add each key-value pair
5. Repeat for `get_contains_mappings()`
6. Save with a descriptive name

## Need Help?

- See `.cursor/rules/preprocessing-system.mdc` for detailed documentation
- Check the Preprocessing Designer page for inline examples
- Test templates with a small dataset first

## Do NOT Modify These Files

Changes to these Python files **will not affect the system**. They are not imported or used in the application code.

Use the Preprocessing Designer UI instead.
