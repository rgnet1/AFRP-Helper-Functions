# Browser-Level Cache Feature

## Overview
Implemented browser-level caching using localStorage to remember user selections across sessions. Users can now leave the Badge Generator V2 page and return to find all their previous selections preserved.

## Cached Data

The following user preferences are saved and restored:

1. **Main Event (Campaign)** - Selected campaign ID
2. **Preprocessing Template** - Selected preprocessing template ID
3. **Sub-Event** - Selected sub-event ID
4. **Contact IDs Filter** - Text input for filtering by contact IDs
5. **Registration Date Filter** - Date filter input
6. **Badge Template** - Selected badge template ID
7. **Avery Template** - Selected Avery label template

## Implementation Details

### Storage Key
```javascript
const CACHE_KEY = 'badgeGeneratorV2_preferences';
```

All preferences are stored as a single JSON object in localStorage under this key.

### Core Functions

#### 1. `saveToCache()`
Collects current form values and saves them to localStorage.

```javascript
function saveToCache() {
    const preferences = {
        campaignId: document.getElementById('campaignSelect')?.value || '',
        preprocessingTemplateId: document.getElementById('preprocessingSelect')?.value || '',
        subEventId: document.getElementById('subEventSelect')?.value || '',
        contactIdsFilter: document.getElementById('inclusionList')?.value || '',
        dateFilter: document.getElementById('createdOnFilter')?.value || '',
        badgeTemplateId: document.getElementById('badgeTemplateSelect')?.value || '',
        averyTemplate: document.getElementById('averyTemplateSelect')?.value || ''
    };
    localStorage.setItem(CACHE_KEY, JSON.stringify(preferences));
}
```

#### 2. `loadFromCache()`
Retrieves saved preferences from localStorage.

```javascript
function loadFromCache() {
    const cached = localStorage.getItem(CACHE_KEY);
    if (cached) {
        return JSON.parse(cached);
    }
    return null;
}
```

#### 3. `restorePreferences(preferences)`
Restores saved values to form fields.

**Key Features:**
- Validates that options exist before setting values
- Triggers change events to update dependent fields
- Uses delays for sub-events (wait for them to load)
- Updates button states after restoration

```javascript
function restorePreferences(preferences) {
    if (!preferences) return;
    
    // Restore each field if value exists in dropdown
    if (preferences.campaignId) {
        const campaignSelect = document.getElementById('campaignSelect');
        if (campaignSelect.querySelector(`option[value="${preferences.campaignId}"]`)) {
            campaignSelect.value = preferences.campaignId;
            campaignSelect.dispatchEvent(new Event('change')); // Trigger sub-event load
        }
    }
    // ... restore other fields ...
    
    // Update UI states
    updateProcessButton();
    updateBadgeButtons();
}
```

## Save Triggers

Preferences are automatically saved when:

### 1. **Campaign Selection Changes**
- Integrated into existing campaign change listener
- Triggers sub-event loading
- Saves immediately

### 2. **Preprocessing Template Changes**
- Saves on dropdown change

### 3. **Sub-Event Selection Changes**
- Saves on dropdown change

### 4. **Filter Text Changes** (Debounced)
- Contact IDs Filter
- Registration Date Filter
- 500ms debounce to avoid excessive saves while typing

```javascript
let filterSaveTimeout;
const saveFiltersDebounced = () => {
    clearTimeout(filterSaveTimeout);
    filterSaveTimeout = setTimeout(saveToCache, 500);
};
```

### 5. **Badge Template Changes**
- Integrated with updateBadgeButtons()
- Saves immediately

### 6. **Avery Template Changes**
- Saves on dropdown change

## Restore Process

### Timing
Preferences are restored **1.5 seconds** after page load:

```javascript
setTimeout(() => {
    const preferences = loadFromCache();
    if (preferences) {
        restorePreferences(preferences);
    }
}, 1500);
```

**Why 1.5 seconds?**
- Allows all dropdowns to load data from API
- Ensures options are available before restoration
- Campaign → triggers sub-events → waits additional 1s for sub-events

### Restoration Order

1. **Campaign** (triggers sub-event loading)
2. **Preprocessing Template**
3. **Sub-Event** (delayed by 1s to allow loading)
4. **Filters** (Contact IDs, Date)
5. **Badge Template** (triggers badge button updates)
6. **Avery Template**
7. **Update button states**

## Error Handling

### Try-Catch Blocks
All cache operations are wrapped in try-catch to handle:
- localStorage not available (private browsing)
- JSON parse errors
- Missing DOM elements

```javascript
try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(preferences));
} catch (error) {
    console.error('Error saving to cache:', error);
}
```

### Validation
Before setting values:
- Checks if element exists
- Checks if option exists in dropdown
- Falls back gracefully if validation fails

## User Experience

### Before Cache Feature
1. User selects campaign
2. User configures all options
3. User generates badges
4. User navigates away
5. **User returns** → All selections lost, must start over

### After Cache Feature
1. User selects campaign
2. User configures all options
3. User generates badges
4. User navigates away
5. **User returns** → All selections restored automatically! ✅

## Benefits

1. **Time Savings**
   - No need to re-select everything
   - Immediate continuation of work

2. **Error Prevention**
   - Reduces risk of selecting wrong campaign
   - Maintains consistent configuration

3. **Better UX**
   - Seamless workflow
   - Works across browser sessions
   - Survives page refreshes

4. **Production-Ready**
   - Handles errors gracefully
   - Non-intrusive (silent operation)
   - Console logging for debugging

## Browser Compatibility

Works in all modern browsers that support:
- `localStorage` (IE8+, all modern browsers)
- `JSON.stringify/parse` (IE8+, all modern browsers)

Falls back gracefully if localStorage is unavailable (e.g., private browsing mode).

## Data Persistence

### When Data is Saved
- Persists across browser sessions
- Survives page refreshes
- Survives browser restarts

### When Data is Cleared
- User clears browser data/cache
- User uses private/incognito mode (not persisted)
- localStorage is manually cleared

## Console Logging

For debugging, the feature logs to console:

```
Saved preferences to cache: {campaignId: "...", ...}
Loaded preferences from cache: {campaignId: "...", ...}
Restored user preferences from cache
```

These logs help verify the cache is working correctly.

## Testing

### Manual Test Flow

1. **Initial Setup**
   - Go to http://localhost:5066/badges-v2
   - Select a campaign
   - Select preprocessing template
   - Select sub-event
   - Enter contact IDs
   - Select badge template
   - Select Avery template

2. **Verify Save**
   - Open browser DevTools → Console
   - Look for "Saved preferences to cache" logs
   - Check localStorage: `localStorage.getItem('badgeGeneratorV2_preferences')`

3. **Verify Restore**
   - Refresh the page (F5)
   - Wait 1.5 seconds
   - All selections should be restored
   - Check console: "Restored user preferences from cache"

4. **Verify Persistence**
   - Close browser tab
   - Reopen http://localhost:5066/badges-v2
   - Selections should still be restored

## Files Modified

- `templates/badges_v2.html`:
  - Added `saveToCache()` function
  - Added `loadFromCache()` function
  - Added `restorePreferences()` function
  - Integrated cache saving into existing event listeners
  - Added debounced save for text inputs
  - Added cache restoration on page load

## Technical Notes

### Why localStorage?
- **Simple**: Key-value storage with JSON
- **Persistent**: Survives browser restarts
- **Browser-Level**: No server-side storage needed
- **Fast**: Synchronous access
- **Sufficient**: ~5-10MB storage (plenty for our use case)

### Why Not Cookies?
- Cookies sent with every request (unnecessary overhead)
- Smaller storage limit (4KB)
- More complex API

### Why Not sessionStorage?
- sessionStorage cleared when tab closes
- We want persistence across sessions

### Debouncing
Text inputs use debouncing to avoid saving on every keystroke:
- Waits 500ms after user stops typing
- Reduces localStorage writes
- Better performance

## Future Enhancements (Optional)

- [ ] Add "Clear Preferences" button
- [ ] Export/Import preferences
- [ ] Multiple saved configurations (profiles)
- [ ] Last used timestamp
- [ ] Cache expiration (auto-clear after X days)
- [ ] Sync preferences across devices (requires backend)

## Conclusion

The browser-level cache feature significantly improves user experience by remembering selections across sessions. Implementation is clean, error-resistant, and follows best practices for localStorage usage.

**Key Achievement:** Users can now seamlessly continue their work from where they left off, making the Badge Generator V2 much more user-friendly for repeated use.
