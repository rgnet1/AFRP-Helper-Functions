# Template Duplicate Feature

## Overview
Added duplicate functionality for both preprocessing templates and badge templates. Users can now easily create copies of existing templates with auto-incremented names.

## Features

### 1. **Smart Name Auto-Increment**
When duplicating a template, the system automatically generates a unique name:
- First duplicate: `Original Name (1)`
- Second duplicate: `Original Name (2)`
- Third duplicate: `Original Name (3)`
- And so on...

### 2. **Context-Aware Button**
The duplicate button:
- ✅ **Shows** when editing an existing template
- ❌ **Hides** when creating a new template
- Located in the action buttons area for easy access

### 3. **Complete Copy**
Duplicates include **all** template data:

**For Preprocessing Templates:**
- Template name (auto-incremented)
- Description
- Value mappings
- Contains mappings

**For Badge Templates:**
- Template name (auto-incremented)
- SVG filename
- Club logo filename
- Column mappings
- Avery template selection

## How to Use

### Preprocessing Templates (`/preprocessing-designer`)

1. **Load an existing template** by clicking it in the sidebar
2. **Duplicate button appears** in the action buttons
3. **Click "Duplicate"**
4. **New template is created** with auto-incremented name
5. **New template loads** automatically for editing

### Badge Templates (`/badge-mapping`)

1. **Load an existing template** from the saved templates dropdown
2. **Duplicate button appears** in the action buttons
3. **Click "Duplicate"**
4. **New template is created** with auto-incremented name
5. **New template loads** automatically for editing

## Backend Implementation

### API Endpoints

#### Preprocessing Templates
```
POST /api/preprocessing-templates/<id>/duplicate
```
**Response:**
```json
{
  "success": true,
  "message": "Template duplicated successfully",
  "template": {
    "id": 3,
    "name": "Original Name (1)",
    "description": "...",
    "value_mappings": {...},
    "contains_mappings": {...}
  }
}
```

#### Badge Templates
```
POST /api/badge-templates/<id>/duplicate
```
**Response:**
```json
{
  "success": true,
  "message": "Template duplicated successfully",
  "template": {
    "id": 5,
    "name": "Original Name (1)",
    "svg_filename": "...",
    "column_mappings": {...},
    "avery_template": "5392"
  }
}
```

### Auto-Increment Algorithm

```python
# Generate new name with auto-increment
base_name = template.name
new_name = base_name
counter = 1

while TemplateModel.query.filter_by(name=new_name).first():
    new_name = f"{base_name} ({counter})"
    counter += 1

# new_name is now unique
```

## UI Components

### Button HTML
```html
<button class="btn btn-secondary" id="duplicateBtn" style="display: none;">
    <i class="fas fa-copy"></i> Duplicate
</button>
```

### Show/Hide Logic

**Show when loading template:**
```javascript
document.getElementById('duplicateBtn').style.display = 'inline-flex';
```

**Hide when creating new:**
```javascript
document.getElementById('duplicateBtn').style.display = 'none';
```

### Duplicate Function
```javascript
async function duplicateTemplate() {
    if (!editingTemplateId) {
        showToast('No template selected to duplicate', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/preprocessing-templates/${editingTemplateId}/duplicate`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to duplicate template');
        }
        
        const result = await response.json();
        showToast(result.message || 'Template duplicated successfully!', 'success');
        
        await loadTemplates();
        // Load the newly created template
        loadTemplate(result.template.id);
    } catch (error) {
        console.error('Error duplicating template:', error);
        showToast('Failed to duplicate template: ' + error.message, 'error');
    }
}
```

## Examples

### Example 1: First Duplicate
- **Original**: "Lexington 2026"
- **Duplicate**: "Lexington 2026 (1)"

### Example 2: Multiple Duplicates
- **Original**: "Convention 2025"
- **1st Duplicate**: "Convention 2025 (1)"
- **2nd Duplicate**: "Convention 2025 (2)"
- **3rd Duplicate**: "Convention 2025 (3)"

### Example 3: Duplicate of Duplicate
- **Original**: "Minimal Badge"
- **1st Duplicate**: "Minimal Badge (1)"
- **Duplicate of (1)**: "Minimal Badge (1) (1)"

## Files Modified

### Backend (`app.py`)
1. Added `/api/preprocessing-templates/<id>/duplicate` endpoint
2. Added `/api/badge-templates/<id>/duplicate` endpoint
3. Implemented auto-increment naming logic

### Preprocessing Designer (`templates/preprocessing_designer.html`)
1. Added duplicate button to action buttons
2. Implemented show/hide logic in `newTemplate()` and `loadTemplate()`
3. Added `duplicateTemplate()` async function
4. Connected button click event to function

### Badge Mapping (`templates/badge_mapping.html`)
1. Added duplicate button to action buttons
2. Implemented show/hide logic in `resetForm()` and `loadTemplate()`
3. Added `duplicateTemplate()` async function
4. Connected button click event to function

## User Experience

### Before Duplicate Feature
1. Load existing template
2. Manually change the name
3. Save as new template
4. Risk of forgetting to change name → overwrite error

### After Duplicate Feature
1. Load existing template
2. Click "Duplicate" button
3. ✅ New template created automatically with unique name
4. ✅ Ready to edit without worrying about name conflicts

## Benefits

1. **Faster Workflow**: One-click duplication vs manual copy
2. **No Name Conflicts**: Auto-increment ensures uniqueness
3. **Less Errors**: No risk of accidentally overwriting templates
4. **Better UX**: Clear visual feedback with toast notifications
5. **Consistency**: Same feature across both template types

## Testing Checklist

✅ Duplicate preprocessing template
✅ Duplicate badge template
✅ Auto-increment works (1, 2, 3...)
✅ Button shows/hides correctly
✅ All template data copied
✅ New template loads after duplication
✅ Error handling (no template selected)
✅ Multiple duplicates of same template
✅ Duplicate button hidden when creating new

## Future Enhancements (Optional)

- [ ] Bulk duplicate (duplicate multiple templates at once)
- [ ] Custom duplicate name (let user specify name during duplication)
- [ ] Duplicate with modifications (open modal to make changes before saving)
- [ ] Duplicate history (track which templates were duplicated from which)
- [ ] Cross-type duplication (use preprocessing template from different event)

## Conclusion

The duplicate feature streamlines the template creation process by allowing users to quickly create copies of existing templates with automatically generated unique names. This reduces errors, saves time, and provides a better user experience for both preprocessing and badge template management.
