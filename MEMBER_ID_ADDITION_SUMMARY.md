# Member ID Field Addition Summary

## Problem Statement
Badge Generator V2 was missing the Member ID column (format: `ID-####`) that exists in Badge Generator V1's output.

## Discovery Process

### Step 1: Identified the Need
Compared Badge V1 and V2 outputs and found missing contact ID in format `ID-####`.

### Step 2: Created Debug Endpoint
Added temporary debug endpoint in `app.py` to explore all Dynamics CRM contact fields:

```python
@app.route('/api/debug/contact-fields', methods=['GET'])
def debug_contact_fields():
    """Debug endpoint to discover contact fields in Dynamics."""
    # Returns all available fields on a sample contact
```

### Step 3: Queried for the Field
Used curl to search for the field:
```bash
curl -s http://localhost:5066/api/debug/contact-fields | python3 -m json.tool | grep -i "number\|id"
```

**Found:** `"aha_memberid": "ID-02100"` ✅

### Step 4: Added Field to Data Extraction
Updated `utils/dynamics_crm.py` (2 locations):

```python
# Added aha_memberid to $select clause
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_localclub,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)"
```

### Step 5: Mapped API Field to Excel Column
Updated `utils/dynamics_crm.py` `_map_event_guest_columns()`:

```python
column_mapping = {
    'contact_aha_memberid': 'Member ID (Existing Contact) (Contact)',
    # ... other mappings
}
```

### Step 6: Added to Column Definitions
Updated `utils/badges/convert_to_mail_merge_v3.py`:

```python
class RegistrationColumns:
    MEMBER_ID = "Member ID (Existing Contact) (Contact)"
    
    MAPPINGS = {
        'Member ID': [MEMBER_ID, 'Member ID', 'ID'],
        # ... other mappings
    }
```

### Step 7: Included in Output
Updated processing to include Member ID in output:

```python
unique_columns = ['Contact ID', 'Member ID', 'First Name', 'Last Name', 'Title', 'Local Club', 'Gender', 'Age']
```

### Step 8: Updated Base Classes
Updated `utils/badges/pre_processing_module.py`:

```python
CONTACT_COLUMNS = [
    'Contact ID',
    'Member ID',  # NEW
    'First Name',
    # ... other columns
]
```

### Step 9: Updated Utilities
Updated `utils/badges/event_statistics.py` to exclude Member ID from event column processing.

## Files Modified

1. ✅ `app.py` - Added debug endpoint
2. ✅ `utils/dynamics_crm.py` - Added field to extraction and mapping (2 locations)
3. ✅ `utils/badges/convert_to_mail_merge_v3.py` - Added column definition and mapping
4. ✅ `utils/badges/pre_processing_module.py` - Added to core columns
5. ✅ `utils/badges/event_statistics.py` - Updated exclusion list

## Result
Member ID column now appears in Badge Generator V2 output spreadsheet with values in format `ID-####`, matching Badge Generator V1 behavior.

## Column Position in Output
The Member ID appears as the 2nd column:
1. Contact ID (GUID)
2. **Member ID (ID-####)** ← NEW
3. First Name
4. Last Name
5. Title
6. Local Club
7. Gender
8. Age
9. [Event columns...]

## Future Reference
See `.cursor/skills/dynamics-column-discovery/SKILL.md` for the complete process documentation to add additional columns.
