# Column Mapping Fix for Badge Generator V2

## Problem
When pulling data from Dynamics 365 CRM via the API, the column names don't match what the processing code expects.

**Expected columns (from manual Excel export):**
```
First Name (Existing Contact) (Contact)
Last Name (Existing Contact) (Contact)
Title (Existing Contact) (Contact)
Local Club (Existing Contact) (Contact)
Gender (Existing Contact) (Contact)
Age (Existing Contact) (Contact)
Event
Status Reason
Created On
```

**Actual API columns:**
```
attendeefirstname
attendeelastname
statuscode (numeric, not text like "Paid")
createdon
_existingcontact_value (just the GUID, not the Contact data)
```

## Root Cause
1. **Manual Excel export** provides:
   - Friendly column names with entity relationships shown in parentheses
   - Related Contact entity data (Title, Local Club, Gender, Age) automatically joined
   - Option set values as text (e.g., "Paid" instead of numeric code)

2. **API direct access** provides:
   - Raw field names (e.g., `attendeefirstname`)
   - Only lookup GUIDs, not related entity data
   - Option set values as numbers (e.g., `statuscode: 1`)

## Solution Implemented

### 1. Added `$expand` Query
Updated `get_event_guests()` to expand related entities:

```python
expand_query = "$expand=existingcontact($select=contactid,firstname,lastname,jobtitle,aha_localclub,aha_gender,aha_age),event($select=aha_name)"
```

This pulls the related Contact and Event data in a single query.

### 2. Added Formatted Value Support
Updated `_make_request()` to include the Prefer header:

```python
"Prefer": 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
```

This returns both raw values AND formatted text values:
- `statuscode`: 1 (numeric)
- `statuscode@OData.Community.Display.V1.FormattedValue`: "Paid" (text)

### 3. Updated `_process_response()`
Now uses formatted values when available:

```python
formatted_suffix = "@OData.Community.Display.V1.FormattedValue"
if formatted_key in record:
    processed_record[key] = record[formatted_key]  # Use "Paid" instead of 1
```

### 4. Added `_flatten_expanded_columns()`
Flattens nested JSON from `$expand` queries:

```python
# Input: df['existingcontact'] = {'firstname': 'John', 'lastname': 'Doe'}
# Output: df['existingcontact_firstname'] = 'John', df['existingcontact_lastname'] = 'Doe'
```

### 5. Added `_map_event_guest_columns()`
Maps API field names to Excel column names:

```python
column_mapping = {
    'existingcontact_firstname': 'First Name (Existing Contact) (Contact)',
    'existingcontact_lastname': 'Last Name (Existing Contact) (Contact)',
    'existingcontact_jobtitle': 'Title (Existing Contact) (Contact)',
    'existingcontact_aha_localclub': 'Local Club (Existing Contact) (Contact)',
    'existingcontact_aha_gender': 'Gender (Existing Contact) (Contact)',
    'existingcontact_aha_age': 'Age (Existing Contact) (Contact)',
    'event_aha_name': 'Event',
    'statuscode': 'Status Reason',  # Now contains "Paid" text
    'createdon': 'Created On',
}
```

## Files Modified
- `/home/rumz/git/qr_code_generator/utils/dynamics_crm.py`

## Changes Made

### Before:
```python
def get_event_guests(self, view_id: str) -> pd.DataFrame:
    endpoint = f"crca7_eventguests"
    response = self._make_request(endpoint)
    return self._process_response(response, "crca7_")
```

### After:
```python
def get_event_guests(self, view_id: str) -> pd.DataFrame:
    expand_query = "$expand=existingcontact($select=contactid,firstname,lastname,jobtitle,aha_localclub,aha_gender,aha_age),event($select=aha_name)"
    endpoint = f"crca7_eventguests?{expand_query}"
    response = self._make_request(endpoint)
    df = self._process_response(response, "crca7_")
    df = self._flatten_expanded_columns(df)
    df = self._map_event_guest_columns(df)
    return df
```

## Testing
1. Navigate to http://localhost:5066 (or your server IP)
2. Click "Badge Generator V2"
3. Select "Convention 2025" from dropdown
4. Click "Pull & Process Data from CRM"
5. Check the logs: `docker-compose logs -f afrp-helper`

## Expected Behavior
- ✅ Data pulls successfully from all 4 entities
- ✅ Columns are properly mapped
- ✅ "Status Reason" contains "Paid" (not numeric code)
- ✅ Contact data (Title, Local Club, Gender, Age) is included
- ✅ Event name is included (not just GUID)
- ✅ Processing completes without "Missing required columns" error
- ✅ MAIL_MERGE Excel file downloads successfully

## If Issues Persist

### Check Logs for Specific Errors:
```bash
docker-compose logs --tail=100 afrp-helper | grep -A 10 "ERROR"
```

### Verify Contact Entity Field Names:
The Contact entity might use different field names than expected. You can discover them with this query:

```python
# In your CRM, go to Settings > Customizations > Customize the System
# Find the "Contact" entity
# Check these field names:
# - jobtitle (Title)
# - aha_localclub (Local Club)
# - aha_gender (Gender)
# - aha_age (Age)
```

### Alternative: Check Entity Metadata:
```bash
# In browser, navigate to:
https://afrp.crm.dynamics.com/api/data/v9.2/EntityDefinitions(LogicalName='contact')/Attributes
# Look for the LogicalName of each field
```

## Next Steps (If Needed)
1. **If field names are different**, update the `$select` in `expand_query`
2. **If additional columns are needed**, add them to the column_mapping
3. **For other entities** (QR Codes, Seating, Form Responses), apply similar mapping if needed

## Status
- ✅ Code updated
- ✅ Docker container rebuilt
- ✅ Container running on port 5066
- ⏳ Awaiting user test of pull & process workflow

---

**Last Updated**: 2026-01-12  
**Docker Image**: afrp-helper:latest (SHA: 48bd4375)
