# Dynamics CRM Column Discovery Process

## Overview
This skill documents the step-by-step process for discovering and adding new columns from Dynamics 365 CRM to the Badge Generator V2 output spreadsheet.

## When to Use This Skill
- User requests a new column to be added to output spreadsheet
- Comparing Badge V1 vs V2 output and finding missing columns
- Need to identify the correct Dynamics CRM field name for a specific data point
- User describes data format (e.g., "ID-####") but doesn't know the field name

## Step-by-Step Discovery Process

### Step 1: Create a Debug Endpoint
First, create a temporary debug endpoint in `app.py` to explore all available fields on a Dynamics entity:

```python
@app.route('/api/debug/contact-fields', methods=['GET'])
def debug_contact_fields():
    """Debug endpoint to discover contact fields in Dynamics."""
    try:
        crm_client = DynamicsCRMClient()
        
        # Get first contact with all fields
        endpoint = "contacts?$top=1"
        response = crm_client._make_request(endpoint)
        records = response.get('value', [])
        
        if records:
            contact = records[0]
            fields = {}
            for key, value in contact.items():
                if not key.startswith('@'):
                    fields[key] = str(value)[:100] if value else None
            
            return jsonify({
                'total_fields': len(fields),
                'fields': fields
            })
        else:
            return jsonify({'error': 'No contacts found'}), 404
        
    except Exception as e:
        logger.error(f"Error fetching contact fields: {str(e)}")
        return jsonify({'error': str(e)}), 500
```

### Step 2: Query the Debug Endpoint
Use curl to fetch and inspect all available fields:

```bash
# Rebuild Docker with debug endpoint
docker-compose down && docker-compose up -d --build

# Wait for service to start
sleep 5

# Fetch all contact fields and search for specific patterns
curl -s http://localhost:5066/api/debug/contact-fields | python3 -m json.tool | grep -i "pattern"
```

**Example:** For Member ID in format "ID-####":
```bash
curl -s http://localhost:5066/api/debug/contact-fields | python3 -m json.tool | grep -i "number\|id"
```

**Result found:**
```json
"aha_memberid": "ID-02100"
```

### Step 3: Add Field to CRM Data Extraction
Update the `$expand` query in `utils/dynamics_crm.py` to include the new field:

**Before:**
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_localclub,gendercode,crca7_age),crca7_Event($select=name)"
```

**After:**
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,lastname,salutation,aha_localclub,gendercode,crca7_age,aha_memberid),crca7_Event($select=name)"
```

**Note:** This appears twice in the file (for `get_event_guests()` and `get_event_guests_by_campaign()`), so use `replace_all=True`.

### Step 4: Map API Field to Excel Column Name
Add the field mapping in `utils/dynamics_crm.py` in the `_map_event_guest_columns()` method:

```python
column_mapping = {
    'contact_contactid': 'Contact ID',
    'contact_aha_memberid': 'Member ID (Existing Contact) (Contact)',  # NEW
    'contact_firstname': 'First Name (Existing Contact) (Contact)',
    'contact_lastname': 'Last Name (Existing Contact) (Contact)',
    'contact_salutation': 'Title (Existing Contact) (Contact)',
    'contact_aha_localclub': 'Local Club (Existing Contact) (Contact)',
    'contact_gendercode': 'Gender (Existing Contact) (Contact)',
    'contact_crca7_age': 'Age (Existing Contact) (Contact)',
    'event_name': 'Event',
    'statuscode': 'Status Reason',
    'createdon': 'Created On',
    'name': 'Name',
}
```

### Step 5: Add to Column Mappings
Update `utils/badges/convert_to_mail_merge_v3.py` to include the new field in the mapping class:

```python
class RegistrationColumns:
    CONTACT_ID = "Contact ID (Existing Contact) (Contact)"
    MEMBER_ID = "Member ID (Existing Contact) (Contact)"  # NEW
    FIRST_NAME = "First Name (Existing Contact) (Contact)"
    # ... other fields ...
    
    MAPPINGS = {
        'Contact ID': [CONTACT_ID, 'Contact ID', 'Contact'],
        'Member ID': [MEMBER_ID, 'Member ID', 'ID'],  # NEW
        'First Name': [FIRST_NAME],
        # ... other mappings ...
    }
```

### Step 6: Include in Output Columns
Add the field to the unique columns list in the `process_registration_data()` method:

**Before:**
```python
unique_columns = ['Contact ID', 'First Name', 'Last Name', 'Title', 'Local Club', 'Gender', 'Age']
```

**After:**
```python
unique_columns = ['Contact ID', 'Member ID', 'First Name', 'Last Name', 'Title', 'Local Club', 'Gender', 'Age']
```

### Step 7: Update Core Contact Columns
Update the base preprocessing module `utils/badges/pre_processing_module.py`:

```python
class PreprocessingBase(ABC):
    CONTACT_COLUMNS = [
        'Contact ID',
        'Member ID',  # NEW
        'First Name', 
        'Last Name', 
        'Title', 
        'Local Club', 
        'Gender', 
        'Age',
        'Cell Phone',
        'QR Code'
    ]
```

### Step 8: Update Statistics/Utility Files
Update any files that reference the core column list (e.g., `utils/badges/event_statistics.py`):

```python
if col not in ['Contact ID', 'Member ID', 'First Name', 'Last Name', 'Title', 'Local Club']:
```

### Step 9: Test the Implementation
```bash
# Rebuild with all changes
docker-compose down && docker-compose up -d --build

# Test by processing a campaign
# The new column should appear in the output Excel file
```

### Step 10: Clean Up (Optional)
Remove or comment out the debug endpoint from `app.py` if not needed for future development.

## Common Dynamics CRM Field Patterns

### Field Naming Convention
- **Custom fields**: Often prefixed with `aha_`, `crca7_`, `new_`, or organization-specific prefixes
- **Standard fields**: Use lowercase names like `contactid`, `firstname`, `lastname`
- **Lookup fields**: Suffixed with `_value` (e.g., `_parentcustomerid_value`)
- **Option sets**: Simple names that return integer codes (use formatted values!)

### Data Type Indicators
- **GUIDs**: Fields ending in `id` (e.g., `contactid`, `campaignid`)
- **Option Sets**: Fields like `statuscode`, `gendercode` (integers representing choices)
- **Currency**: Fields with `_base` suffix for base currency values
- **Dates**: Fields ending in `on` or `date` (e.g., `createdon`, `modifiedon`)

## Important Notes

### 1. Formatted Values
Always request formatted values for option sets:
```python
"Prefer": 'odata.include-annotations="OData.Community.Display.V1.FormattedValue"'
```

Check for formatted values when processing:
```python
formatted_key = f"{key}@OData.Community.Display.V1.FormattedValue"
if formatted_key in record:
    processed_record[key] = record[formatted_key]
else:
    processed_record[key] = value
```

### 1a. **CRITICAL**: Lookup Fields in $expand Queries

#### Problem 1: Can't Explicitly Select Lookups
❌ **WRONG (causes 400 error):**
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname,aha_localclub2),..."
# This causes: 400 Client Error: Bad Request
```

#### Problem 2: Using $select Excludes Lookups
❌ **WRONG (lookup fields excluded):**
```python
expand_query = "$expand=crca7_ExistingContact($select=contactid,firstname),..."
# Lookup fields like _aha_localclub2_value are NOT included!
# You'll get "Missing required columns" errors
```

#### The Solution: Don't Use $select in $expand
✅ **CORRECT:**
```python
expand_query = "$expand=crca7_ExistingContact,crca7_Event($select=name)"
# Expand contact with ALL fields (including lookups)
# Still use $select for other entities if needed
```

**Why:** 
- When you use `$select` in `$expand`, you get ONLY the fields you select
- Lookup fields (like `_aha_localclub2_value`) are NOT automatically included
- Without `$select`, all fields including lookups come through
- Formatted values are retrieved via the Prefer header

**Trade-off:** More data is returned, but lookup fields are guaranteed to be included

### 2. Expanded Entities
When accessing fields from expanded entities (like contacts in event guests), the field name gets prefixed:
- Raw API field: `aha_memberid` in the `crca7_ExistingContact` entity
- After flattening: `contact_aha_memberid`

### 3. Column Name Consistency
Use consistent naming pattern for Excel columns:
```
[Field Description] ([Entity Name]) ([Entity Type])
```
Example: `"Member ID (Existing Contact) (Contact)"`

### 4. Handle Missing Fields Gracefully
Always include alternative column names in MAPPINGS to handle different data sources:
```python
'Member ID': [MEMBER_ID, 'Member ID', 'ID', 'MemberID']
```

## Troubleshooting

### Field Not Appearing in Output
1. ✅ Check: Field added to `$expand` query's `$select` clause
2. ✅ Check: Field mapped in `_map_event_guest_columns()`
3. ✅ Check: Field added to `RegistrationColumns.MAPPINGS`
4. ✅ Check: Field included in `unique_columns` list
5. ✅ Check: Docker container rebuilt after changes

### Field Shows as Blank/Null
- May not be populated for all contacts
- Check if field is from expanded entity (needs proper flattening)
- Verify field name is correct (case-sensitive!)

### Field Shows Integer Instead of Text
- Option set field not using formatted value
- Update `_flatten_expanded_columns()` to extract formatted values
- Ensure `Prefer` header includes FormattedValue annotation

## Related Files
- `/home/rumz/git/qr_code_generator/utils/dynamics_crm.py` - CRM data extraction
- `/home/rumz/git/qr_code_generator/utils/badges/convert_to_mail_merge_v3.py` - Column mappings
- `/home/rumz/git/qr_code_generator/utils/badges/pre_processing_module.py` - Base column definitions
- `/home/rumz/git/qr_code_generator/app.py` - API endpoints (including debug)

## Example Use Case: Adding Member ID

**User Request:** "Add the contact ID column. The IDs are in the format ID-#### where #### are numbers."

**Steps Taken:**
1. Created debug endpoint to list all contact fields
2. Queried endpoint and searched for "number\|id" pattern
3. Found `aha_memberid` with value `"ID-02100"` matching the format
4. Added `aha_memberid` to both `$expand` queries in `dynamics_crm.py`
5. Mapped `contact_aha_memberid` to `'Member ID (Existing Contact) (Contact)'`
6. Added to `RegistrationColumns` class and `MAPPINGS`
7. Added to `unique_columns` list in processing
8. Updated `PreprocessingBase.CONTACT_COLUMNS`
9. Updated `event_statistics.py` exclusion list
10. Rebuilt Docker and tested

**Result:** Member ID now appears in Badge Generator V2 output matching Badge V1 format.
