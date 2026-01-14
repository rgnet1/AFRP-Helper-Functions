# Preprocessing Designer Implementation Summary

## Overview
Successfully upgraded the event preprocessing system from hard-coded Python classes to a user-configurable database-driven system with a visual designer interface.

## What Changed

### 1. **Deprecated Code-Based Preprocessing**
- ❌ **Removed**: Hard-coded preprocessing classes (`Convention2025Preprocessing`, `Lex2026Preprocessing`, etc.)
- ❌ **Removed**: Event selection dropdown in the UI
- ✅ **Kept**: `DefaultPreprocessing` class as the fallback (no custom transformations)

### 2. **New Database-Driven System**
- ✅ Created `PreprocessingTemplate` database model to store user-defined preprocessing configurations
- ✅ Dynamic preprocessor class creation from database templates at runtime
- ✅ Full CRUD API endpoints for template management

### 3. **User Interface**
- ✅ New **Preprocessing Designer** page at `/preprocessing-designer`
- ✅ **Designer** button added to Badge Generator V2
- ✅ Preprocessing template dropdown in Badge Generator V2
- ✅ Sidebar with saved templates
- ✅ Visual interface for creating/editing mappings

## Database Schema

### PreprocessingTemplate Model
```python
id: Integer (Primary Key)
name: String (200, Unique) - Template name
description: Text (Optional) - Description of what the template does
value_mappings: Text (JSON) - Exact match replacements
contains_mappings: Text (JSON) - Substring replacements
created_at: DateTime - Creation timestamp
updated_at: DateTime - Last update timestamp
```

## API Endpoints

### Preprocessing Templates
- `GET /api/preprocessing-templates` - List all templates
- `POST /api/preprocessing-templates` - Create new template
- `GET /api/preprocessing-templates/<id>` - Get specific template
- `PUT /api/preprocessing-templates/<id>` - Update template
- `DELETE /api/preprocessing-templates/<id>` - Delete template

### Page Routes
- `/preprocessing-designer` - Preprocessing template designer UI
- `/badges-v2` - Badge Generator V2 (updated with preprocessing dropdown)

## How It Works

### 1. **Creating a Template**
Users can create preprocessing templates via the designer UI:
- **Value Mappings**: Exact text replacements (e.g., "Steak" → "S")
- **Contains Mappings**: Substring removals (e.g., "- Reserved" → "")

### 2. **Using a Template**
1. Go to Badge Generator V2 (`/badges-v2`)
2. Select a campaign
3. Choose a preprocessing template from dropdown (or use default)
4. Click "Pull All & Process"

### 3. **Runtime Processing**
```python
# If user selects a template:
if preprocessing_template_id:
    template = PreprocessingTemplate.query.get(preprocessing_template_id)
    preprocessor_class = create_preprocessor_from_template(template)
else:
    # Default: no custom transformations
    preprocessor_class = DefaultPreprocessing
```

### 4. **Dynamic Class Creation**
The system creates a preprocessor class dynamically from database template:
```python
class DynamicPreprocessor(PreprocessingBase):
    def get_value_mappings(self):
        return template.value_mappings  # From database
    
    def get_contains_mappings(self):
        return template.contains_mappings  # From database
```

## Features

### Value Mappings (Exact Match)
Replace exact text values:
- **Example 1**: "Steak" → "S" (Shorten meal preference)
- **Example 2**: "No Club Affiliation" → " " (Remove text)
- **Example 3**: "Mid-Year Meeting 2026" → "Lexington 2026" (Simplify name)

### Contains Mappings (Substring Match)
Remove text that appears anywhere in a field:
- **Example 1**: "- Reserved" → "" (Remove reservation note)
- **Example 2**: "Ramallah Federation in " → "" (Remove prefix)
- **Example 3**: "(Ages 13-17)" → "" (Remove age restriction)

## Designer UI Features

### Left Sidebar
- **Saved Templates List**: Click to edit
- **New Template Button**: Create from scratch
- **Delete Button**: Remove unwanted templates (with confirmation)

### Main Panel
- **Template Name**: Required field
- **Description**: Optional context
- **Value Mappings Section**:
  - Add/remove mapping rows
  - Free text input for both fields
  - Examples provided
- **Contains Mappings Section**:
  - Add/remove mapping rows
  - Free text input for both fields
  - Examples provided
- **Save/Clear Buttons**: Manage template state

### UX Enhancements
- **Toast Notifications**: Success/error feedback
- **Active Template Highlighting**: Visual indication of current template
- **Info Banner**: Explains preprocessing concepts
- **Example Boxes**: Provides real-world use cases

## Migration Path

### Old System (Deprecated)
```python
# Hard-coded in Python
class Convention2025Preprocessing(PreprocessingBase):
    def get_value_mappings(self):
        return {"Steak": "S", ...}
```

### New System (Current)
```sql
-- Stored in database
INSERT INTO preprocessing_template (name, value_mappings, contains_mappings)
VALUES ('Convention 2025', '{"Steak": "S", ...}', '{"- Reserved": "", ...}');
```

## Files Modified

### Backend
1. `app.py`:
   - Added `create_preprocessor_from_template()` helper
   - Added preprocessing template CRUD endpoints
   - Updated `badges_v2_pull_and_process()` to use database templates
   - Removed fallback to code-based preprocessors

2. `utils/magazine/scheduler.py`:
   - Added `PreprocessingTemplate` database model

### Frontend
1. `templates/badges_v2.html`:
   - Removed "Event" dropdown (no longer needed)
   - Added preprocessing template dropdown
   - Added "Designer" button
   - Added `loadPreprocessingTemplates()` function
   - Removed `loadAvailableEvents()` function
   - Updated `processData()` to send `preprocessingTemplateId`

2. `templates/preprocessing_designer.html` (NEW):
   - Full designer interface
   - Template management UI
   - Drag-and-drop style interface
   - Real-time saving and loading

### Deprecated (Still Present but Unused)
- `utils/badges/event_preprocessing/convention2025.py`
- `utils/badges/event_preprocessing/lex2026.py`
- `/api/available-events` endpoint (can be removed)

## Testing Checklist

✅ Create a new preprocessing template
✅ Edit an existing template
✅ Delete a template
✅ Use a template in Badge Generator V2
✅ Process data with custom mappings
✅ Process data with default (no template)
✅ Verify mappings are applied correctly in output Excel

## Benefits

1. **No Code Required**: Users can create preprocessing rules without Python knowledge
2. **Instant Updates**: Changes take effect immediately without container rebuild
3. **Reusability**: Templates can be reused across multiple events
4. **Version Control**: Database tracks creation and update timestamps
5. **User-Friendly**: Visual interface is intuitive and self-documenting
6. **Flexible**: Both exact match and substring replacements supported
7. **Safe Defaults**: Falls back to default preprocessing if no template selected

## Future Enhancements (Optional)

- [ ] Template versioning/history
- [ ] Template sharing/export (JSON export/import)
- [ ] Template preview/testing before applying
- [ ] Regex support for advanced pattern matching
- [ ] Template categories/tags
- [ ] Bulk operations (copy template, apply to multiple events)
- [ ] Template validation (warn if mapping keys don't exist in data)

## Conclusion

The preprocessing system has been successfully upgraded from a developer-centric code-based approach to a user-friendly, database-driven system. Users can now create, manage, and apply data transformations through an intuitive visual designer without touching any code.

**Key Achievement**: Complete deprecation of hard-coded preprocessing classes in favor of flexible, user-configurable database templates.
