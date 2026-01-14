# Pull, Process & Generate Badges Button Fix

## Issue
The "Pull, Process & Generate Badges" button was not working - nothing happened when clicked.

## Root Cause
When we removed the "Event" dropdown to upgrade to the database-driven preprocessing system, we forgot to update the `processAndGenerateBadges()` function. This function was still trying to access the removed `eventSelect` dropdown, which caused a JavaScript error and prevented the button from working.

## Specific Errors

### 1. JavaScript Error in Frontend
**File**: `templates/badges_v2.html`  
**Function**: `processAndGenerateBadges()`  
**Line 1177** (before fix):
```javascript
event: document.getElementById('eventSelect').value || 'Default',
```
**Problem**: `eventSelect` element no longer exists in the DOM, causing `document.getElementById('eventSelect')` to return `null`, which then throws an error when trying to access `.value`.

### 2. Missing Preprocessing Template Parameter
The function was not sending the `preprocessingTemplateId` parameter to the backend, so even if it worked, it wouldn't use the user-selected preprocessing template.

### 3. Backend Still Using Old Code-Based Preprocessors
**File**: `app.py`  
**Endpoint**: `/api/badges-v2/pull-process-generate`  
**Line 1559** (before fix):
```python
preprocessor_class = preprocessing_implementations.get(event_name, DefaultPreprocessing)
```
**Problem**: The endpoint was still using the deprecated code-based preprocessing system instead of the new database-driven system.

## Fixes Applied

### Fix 1: Updated Frontend JavaScript
**File**: `templates/badges_v2.html`  
**Function**: `processAndGenerateBadges()`

```javascript
// Before:
const data = {
    campaign_id: campaignId,
    campaign_name: campaignName,
    event: document.getElementById('eventSelect').value || 'Default',  // ❌ ERROR
    subEvent: document.getElementById('subEventSelect').value || null,
    inclusionList: inclusionList,
    createdOnFilter: document.getElementById('createdOnFilter').value || null,
    template_id: parseInt(templateId),
    avery_template: averyTemplate
};

// After:
const data = {
    campaign_id: campaignId,
    campaign_name: campaignName,
    event: 'Default',  // ✅ FIXED: No longer uses removed dropdown
    subEvent: document.getElementById('subEventSelect').value || null,
    inclusionList: inclusionList,
    createdOnFilter: document.getElementById('createdOnFilter').value || null,
    preprocessingTemplateId: document.getElementById('preprocessingSelect').value || null,  // ✅ ADDED
    template_id: parseInt(templateId),
    avery_template: averyTemplate
};
```

### Fix 2: Updated Backend Endpoint
**File**: `app.py`  
**Endpoint**: `/api/badges-v2/pull-process-generate`

```python
# Before:
event_name = data.get('event')
# ... later ...
preprocessor_class = preprocessing_implementations.get(event_name, DefaultPreprocessing)

# After:
event_name = data.get('event', 'Default')
preprocessing_template_id = data.get('preprocessingTemplateId')

# Get the preprocessing implementation from database templates
preprocessor_class = None

# Check if user selected a database template
if preprocessing_template_id:
    try:
        from utils.magazine.scheduler import PreprocessingTemplate
        template = PreprocessingTemplate.query.get(int(preprocessing_template_id))
        if template:
            logger.info(f"Using database preprocessing template: {template.name}")
            preprocessor_class = create_preprocessor_from_template(template)
        else:
            logger.warning(f"Preprocessing template {preprocessing_template_id} not found, using default")
    except Exception as e:
        logger.error(f"Error loading preprocessing template: {str(e)}")

# Use default preprocessing (no custom mappings) if no template selected
if not preprocessor_class:
    logger.info("No preprocessing template selected, using default (no custom transformations)")
    preprocessor_class = DefaultPreprocessing
```

## Testing

### Before Fix
1. Go to http://localhost:5066/badges-v2
2. Select a campaign
3. Select a badge template
4. Click "Pull, Process & Generate Badges"
5. **Result**: ❌ Nothing happens (JavaScript error in console)

### After Fix
1. Go to http://localhost:5066/badges-v2
2. Select a campaign
3. (Optional) Select a preprocessing template
4. Select a badge template
5. Click "Pull, Process & Generate Badges"
6. **Result**: ✅ Button works, data is pulled, processed, and badges are generated

## Related Changes
This fix completes the transition from code-based preprocessing to database-driven preprocessing. Both badge generation workflows now support the new system:

1. ✅ **"Pull All & Process"** button → Uses database preprocessing templates
2. ✅ **"Pull, Process & Generate Badges"** button → Uses database preprocessing templates

## Files Modified
- `templates/badges_v2.html` - Fixed `processAndGenerateBadges()` function
- `app.py` - Updated `/api/badges-v2/pull-process-generate` endpoint

## Conclusion
The button now works correctly and uses the new database-driven preprocessing system. Users can select their preprocessing template from the dropdown, and it will be applied when generating badges.
