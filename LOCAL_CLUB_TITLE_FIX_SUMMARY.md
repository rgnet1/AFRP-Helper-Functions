# Local Club & Title Field Fix Summary

## Problem Statement
Two fields were appearing blank in Badge Generator V2 output:
1. **Local Club** - Always blank
2. **Title** (honorifics like Mr./Mrs./Dr.) - Always blank

## Investigation Process

### Step 1: Updated Debug Endpoint
Modified `/api/debug/contact-fields` to query multiple contacts and extract title and local club fields.

### Step 2: Queried 10 Sample Contacts
Results showed:

**Local Club Fields:**
```json
{
    "aha_localclub": null,  // ❌ Wrong field - always NULL
    "_aha_localclub2_value": "98cd4706-00c4-ed11-83ff-6045bd0069e2",  // GUID
    "_aha_localclub2_formatted": "Detroit"  // ✅ Correct - has club name!
}
```

**Title Fields:**
```json
{
    "salutation": null,  // NULL across all contacts
    "aha_title": null,  // NULL across all contacts
    "jobtitle": "Teacher"  // Has occupation, not honorifics
}
```

### Key Findings:

1. **Local Club**: 
   - We were using `aha_localclub` which doesn't exist/is always NULL
   - The correct field is `aha_localclub2` which is a **lookup field**
   - As a lookup, it stores a GUID but has a formatted value annotation
   - Sample values: "Detroit", "Chicago", "San Francisco", "Louisville", "Houston", "Washington D.C."

2. **Title**:
   - Both `salutation` and `aha_title` are NULL across all sampled contacts
   - This suggests the honorific data may not be populated in the system
   - Added both fields to the query so if either gets populated, it will be captured

## Solution Implemented

### File 1: `utils/dynamics_crm.py`

**Changed $expand query to use correct fields:**

Before:
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_localclub,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)"
```

After (Initial attempt):
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_title,aha_localclub2,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)"
```

**This caused a 400 Bad Request error!**

After (Final fix):
```python
# Note: Don't select lookup fields (like aha_localclub2) in $expand - they come automatically with formatted values
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_title,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)"
```

**Changes:**
- ❌ Removed: `aha_localclub` (doesn't exist)
- ❌ Removed: `aha_localclub2` from $select (lookup fields can't be explicitly selected in $expand)
- ✅ Kept: Lookup field still retrieved automatically with formatted value
- ✅ Added: `aha_title` (alternative title field)
- ✅ Kept: `salutation` (in case it gets populated)

**Updated column mapping:**

```python
column_mapping = {
    'contact_aha_memberid': 'Member ID (Existing Contact) (Contact)',
    'contact_firstname': 'First Name (Existing Contact) (Contact)',
    'contact_lastname': 'Last Name (Existing Contact) (Contact)',
    'contact_salutation': 'Title (Existing Contact) (Contact)',
    'contact_aha_title': 'Title (Existing Contact) (Contact)',  # Alternative mapping
    'contact__aha_localclub2_value': 'Local Club (Existing Contact) (Contact)',  # GUID
    'contact_aha_localclub2': 'Local Club (Existing Contact) (Contact)',  # Lookup field
    'contact_gendercode': 'Gender (Existing Contact) (Contact)',
    'contact_crca7_age': 'Age (Existing Contact) (Contact)',
    # ... other mappings
}
```

## Critical Discovery: Lookup Fields in $expand Queries

### The 400 Bad Request Error
After initially adding `aha_localclub2` to the `$select` clause, we got:
```
400 Client Error: Bad Request for url: ...
$expand=crca7_ExistingContact($select=...,aha_localclub2,...)
```

**Reason:** You **cannot** explicitly select lookup fields in an `$expand` query's `$select` clause!

### The Solution
Remove lookup fields from `$select` - they come **automatically** with the expanded entity:

❌ **Wrong:** `$expand=Entity($select=field1,lookupfield2)`
✅ **Correct:** `$expand=Entity($select=field1)` ← lookup comes anyway!

## Understanding Dynamics Lookup Fields

### How Lookup Fields Work:

1. **In the raw entity**: Lookup fields appear as `_fieldname_value` (e.g., `_aha_localclub2_value`)
2. **When selected in $expand**: They appear without underscore (e.g., `aha_localclub2`)
3. **The value**: Contains a GUID pointing to the related record
4. **Formatted value**: `fieldname@OData.Community.Display.V1.FormattedValue` contains the display name

### Why Our Code Works:

Our `_flatten_expanded_columns()` method already extracts formatted values:

```python
for key, value in contact.items():
    if key.endswith(formatted_suffix):
        continue
    formatted_key = f"{key}{formatted_suffix}"
    if formatted_key in contact:
        processed_contact[key] = contact[formatted_key]  # Use formatted value!
    else:
        processed_contact[key] = value
```

So when we request `aha_localclub2`:
1. Dynamics returns the GUID as `aha_localclub2`
2. Dynamics also returns `aha_localclub2@OData.Community.Display.V1.FormattedValue = "Detroit"`
3. Our code detects the formatted value and uses "Detroit" instead of the GUID
4. After flattening, it becomes `contact_aha_localclub2`
5. Column mapping maps it to `'Local Club (Existing Contact) (Contact)'`

## Expected Results

### Local Club:
✅ Should now display: "Detroit", "Chicago", "San Francisco", etc.

### Title:
⚠️  Will remain blank unless:
- Data is populated in `salutation` or `aha_title` fields in Dynamics
- User manually enters honorifics in Dynamics CRM
- Alternative: Could use `jobtitle` field if occupation is acceptable

## Files Modified

1. ✅ `utils/dynamics_crm.py`
   - Updated $expand query (2 locations)
   - Updated column mapping
   
2. ✅ `app.py`
   - Added debug endpoint to discover fields

## Testing

After rebuild, process a campaign through Badge Generator V2:
- ✅ Local Club column should show club names
- ℹ️  Title column behavior depends on data population in Dynamics

## Recommendations for Title Field

If Title/honorifics are important and currently unpopulated:

**Option 1**: Populate `salutation` or `aha_title` in Dynamics CRM
- Update contact records to include Mr./Mrs./Dr./Ms. values

**Option 2**: Use a different field if acceptable
- Could map `jobtitle` if occupation is useful for badges

**Option 3**: Create custom preprocessing
- Add logic in preprocessing module to derive title from other fields

## Related Documentation

See `.cursor/skills/dynamics-column-discovery/SKILL.md` for the complete process of discovering and adding Dynamics CRM columns.
