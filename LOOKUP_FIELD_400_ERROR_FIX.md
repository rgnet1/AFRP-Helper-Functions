# 400 Bad Request Error - Lookup Field in $expand Fix

## Error Message
```
Failed to pull Event Guests: 400 Client Error: Bad Request for url: 
https://afrp.crm.dynamics.com/api/data/v9.2/crca7_eventguests?
$filter=...&
$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_title,aha_localclub2,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)
```

## Root Cause
The error occurred because we included `aha_localclub2` (a **lookup field**) in the `$select` clause of the `$expand` query. 

Dynamics CRM Web API **does not allow** you to explicitly select lookup fields in an `$expand` query. They come automatically.

## Understanding Lookup Fields in Dynamics CRM

### What is a Lookup Field?
A **lookup field** is a reference to another entity (like a foreign key). For example:
- `aha_localclub2` → References a "Local Club" entity
- Stored internally as `_aha_localclub2_value` (a GUID)
- Has a formatted display name like "Detroit", "Chicago", etc.

### How They Behave in API Queries:

1. **When querying the base entity directly:**
   ```
   /contacts?$select=_aha_localclub2_value
   ```
   - You CAN select `_aha_localclub2_value` (the GUID)
   - Formatted value comes as `_aha_localclub2_value@OData.Community.Display.V1.FormattedValue`

2. **When using $expand on related entities:**
   ```
   /crca7_eventguests?$expand=crca7_ExistingContact($select=aha_localclub2)
   ```
   - ❌ **CANNOT** select lookup fields explicitly
   - ✅ Lookup fields come **automatically** in the expanded entity
   - Their formatted values are included via the Prefer header

## The Fix (Evolution)

### Attempt 1 (Caused 400 Error):
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_title,aha_localclub2,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)"
```
❌ **Error:** 400 Bad Request - Can't explicitly select lookup fields

### Attempt 2 (Removed lookup from $select):
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_title,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)"
```
❌ **Error:** "Missing required columns: Local Club" - Lookup fields NOT included when using `$select`

### Final Fix (Remove $select entirely for contacts):
```python
# Expand with all contact fields to ensure lookup fields (_aha_localclub2_value) are included
# When you use $select in $expand, lookup fields may not be included automatically
expand_query = "$expand=crca7_ExistingContact,crca7_Event($select=name)"
```
✅ **Success:** All fields including lookups are returned!

## How the Data Still Gets Retrieved

Even though we don't select `aha_localclub2`, it still comes in the response:

1. **Automatic Inclusion**: When you expand `crca7_ExistingContact`, ALL fields including lookups are returned
2. **Field Name**: Appears as `_aha_localclub2_value` in the response
3. **Formatted Value**: `_aha_localclub2_value@OData.Community.Display.V1.FormattedValue` = "Detroit"
4. **Our Processing**: 
   - `_flatten_expanded_columns()` extracts the formatted value
   - Prefixes with `contact_` → `contact__aha_localclub2_value`
   - Value is "Detroit" (not the GUID)
5. **Column Mapping**: 
   - Maps `contact__aha_localclub2_value` → `'Local Club (Existing Contact) (Contact)'`

## CRITICAL DISCOVERY: $select in $expand Excludes Lookups!

### The Problem with Using $select in $expand
When you use `$select` within an `$expand` clause:
- ✅ You get ONLY the fields you explicitly select
- ❌ You do NOT get lookup fields automatically
- ❌ Lookup fields are excluded even though they're stored as `_fieldname_value`

### The Solution
**Don't use `$select` in `$expand` if you need lookup fields!**

❌ **With $select (lookups excluded):**
```python
$expand=crca7_ExistingContact($select=contactid,firstname)
# Result: Only contactid and firstname, NO lookup fields!
```

✅ **Without $select (all fields included):**
```python
$expand=crca7_ExistingContact
# Result: ALL fields including _aha_localclub2_value!
```

## Key Lessons

**When using `$expand`:**
1. ❌ **DON'T** include lookup field names in `$select` (causes 400 error)
2. ❌ **DON'T** use `$select` at all if you need lookup fields (they'll be excluded)
3. ✅ **DO** expand without `$select` to get all fields including lookups
4. ✅ **DO** use the Prefer header to get formatted values

```python
headers = {
    "Prefer": 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
}
```

**Trade-off:** Expanding without `$select` returns more data, but ensures lookup fields are included.

## Files Modified

1. ✅ `utils/dynamics_crm.py` - Removed `aha_localclub2` from `$expand` query (2 locations)
2. ✅ `.cursor/skills/dynamics-column-discovery/SKILL.md` - Added warning about lookup fields

## Testing

After the fix:
- ✅ API call succeeds (no 400 error)
- ✅ Local Club data is retrieved automatically
- ✅ Formatted values ("Detroit", "Chicago", etc.) are used instead of GUIDs

## Similar Issues to Watch For

Any field starting with `_` and ending with `_value` is a lookup field:
- `_aha_localclub2_value`
- `_aha_householdid_value`
- `_aha_parentcampaign_value`
- `_existingcontact_value`

**Remember:** Don't include these in `$select` clauses within `$expand` queries!
