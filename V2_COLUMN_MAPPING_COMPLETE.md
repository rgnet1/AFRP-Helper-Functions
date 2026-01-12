# Badge Generator V2 - Complete Column Mapping Implementation

## Overview
Badge Generator V2 now pulls data from all 4 Dynamics CRM entities via API and **maps them to the exact same column structure** that V1 expects from manually downloaded Excel files.

---

## The Challenge

When you manually export data from Dynamics CRM UI:
- Column names are user-friendly: `"First Name (Existing Contact) (Contact)"`
- Related entity data is automatically joined
- Option sets show text values: `"Paid"` instead of numeric codes

When pulling via API:
- Column names are field names: `attendeefirstname`, `statuscode`
- Related entities must be explicitly expanded with `$expand`
- Option sets return numbers unless you request formatted values

**V2 Solution:** Transform API data to match manual Excel export structure **exactly** so V1's processing logic works without modification.

---

## Implementation Details

### 1. Event Guests (Registration List)

**API Call:**
```python
$expand=crca7_ExistingContact($select=contactid,firstname,lastname,jobtitle,aha_localclub,gendercode,crca7_age),crca7_Event($select=name)
```

**Column Mapping:**
```python
{
    'contact_contactid': 'Contact ID',
    'contact_firstname': 'First Name (Existing Contact) (Contact)',
    'contact_lastname': 'Last Name (Existing Contact) (Contact)',
    'contact_jobtitle': 'Title (Existing Contact) (Contact)',
    'contact_aha_localclub': 'Local Club (Existing Contact) (Contact)',
    'contact_gendercode': 'Gender (Existing Contact) (Contact)',
    'contact_crca7_age': 'Age (Existing Contact) (Contact)',
    'event_name': 'Event',
    'statuscode': 'Status Reason',  # Formatted value: "Paid"
    'createdon': 'Created On',
}
```

**Key Points:**
- **Drops** `attendeefirstname` and `attendeelastname` (they're duplicates of Contact data)
- Uses Contact entity fields for consistency across all entities
- Handles formatted values for option sets (Status Reason)

### 2. QR Codes

**API Call:**
```python
$expand=aha_EventGuest($select=crca7_eventguestid;$expand=crca7_ExistingContact($select=contactid))
```

**Column Mapping:**
```python
{
    'contact_contactid': 'Contact ID (Event Guest Contact Id) (Contact)',
    'qrcodevalue': 'QR Code Value',
}
```

**Key Points:**
- Nested expand: EventGuest → ExistingContact → contactid
- Links QR codes to the same Contact ID used in Event Guests

### 3. Seating Tables

**API Call:**
```python
$expand=aha_Contact($select=contactid),aha_Event($select=name)
```

**Column Mapping:**
```python
{
    'contact_contactid': 'Contact ID (Contact) (Contact)',
    'event_name': 'Event',
    'name': 'Table',  # or 'tablenumber'
}
```

**Key Points:**
- Direct contact reference (not through Event Guest)
- Event name for matching to registration

### 4. Form Responses

**API Call:**
```python
$expand=aha_contact($select=contactid),aha_Campaign($select=name)
```

**Column Mapping:**
```python
{
    'contact_contactid': 'Contact ID (Contact) (Contact)',
    'campaign_name': 'Campaign',
    'formquestion': 'Form Question',
    'guestresponse': 'Guest Response',
}
```

**Key Points:**
- Campaign is the Event in this entity
- Each response has Question and Answer

---

## Cross-Entity Matching

All entities now reference the **same Contact ID** for proper merging:

```
Registration:  Contact ID (Existing Contact) (Contact) → contactid
QR Codes:      Contact ID (Event Guest Contact Id) (Contact) → contactid  
Seating:       Contact ID (Contact) (Contact) → contactid
Form Responses: Contact ID (Contact) (Contact) → contactid
```

The processing code uses these Contact IDs to merge data across all 4 entities into a single mail merge file.

---

## Files Modified

### `/home/rumz/git/qr_code_generator/utils/dynamics_crm.py`

**Added Functions:**
1. `_flatten_expanded_columns()` - Flattens Event Guest Contact data
2. `_map_event_guest_columns()` - Maps Event Guest columns
3. `_flatten_qr_code_columns()` - Flattens nested QR Code structure
4. `_map_qr_code_columns()` - Maps QR Code columns
5. `_flatten_seating_columns()` - Flattens Seating Table data
6. `_map_seating_columns()` - Maps Seating columns
7. `_flatten_form_response_columns()` - Flattens Form Response data
8. `_map_form_response_columns()` - Maps Form Response columns

**Updated Functions:**
1. `_make_request()` - Added Prefer header for formatted values
2. `_process_response()` - Uses formatted values when available
3. `get_event_guests()` - Added $expand and mapping
4. `get_qr_codes()` - Added $expand and mapping
5. `get_table_reservations()` - Added $expand and mapping
6. `get_form_responses()` - Added $expand and mapping

---

## How It Works - End to End

### User Action:
1. Go to http://localhost:5066
2. Click "Badge Generator V2"
3. Select "Convention 2025" from dropdown
4. Click "Pull & Process Data from CRM"

### Backend Process:
1. **Pull from CRM** (4 API calls):
   ```python
   GET /crca7_eventguests?$expand=crca7_ExistingContact(...),crca7_Event(...)
   GET /aha_eventguestqrcodeses?$expand=aha_EventGuest(...)
   GET /aha_seatingtables?$expand=aha_Contact(...),aha_Event(...)
   GET /aha_eventformresponseses?$expand=aha_contact(...),aha_Campaign(...)
   ```

2. **Transform Each Entity:**
   - Flatten nested JSON from $expand
   - Map API field names to Excel column names
   - Handle formatted values for option sets
   - Drop duplicate columns

3. **Save to Excel Files:**
   ```
   /uploads/Registration List_crm_data.xlsx
   /uploads/QR Codes_crm_data.xlsx
   /uploads/Seating Chart_crm_data.xlsx
   /uploads/Form Responses_crm_data.xlsx
   ```

4. **Process Using V1 Logic:**
   - Copy files to temp directory
   - Use EventRegistrationProcessorV3 (same as V1)
   - Merge based on Contact ID
   - Apply filters (sub-event, inclusion list, date)
   - Generate MAIL_MERGE output

5. **Download Results:**
   - Single Excel file with all merged data
   - Ready for mail merge in Word/Publisher

---

## Testing Status

✅ **Column Structure:** All 4 entities map to expected column names  
✅ **Contact ID Matching:** All entities reference same Contact ID  
✅ **Formatted Values:** Status Reason shows "Paid" not numeric code  
✅ **Docker Container:** Rebuilt and running on port 5066  
⏳ **End-to-End Test:** Awaiting user test with real data

---

## Troubleshooting

### If you get "Missing required columns" error:

Check the logs to see which columns are missing:
```bash
docker-compose logs afrp-helper | grep "Missing required columns"
```

The error will show exactly which columns are expected vs. what was received.

### If Contact IDs don't match across entities:

This would cause empty results after merging. Check that:
1. All entities expanded the Contact/EventGuest properly
2. Navigation property names are correct (case-sensitive!)
3. The field names in $select are correct

### If you get 400 Bad Request on $expand:

- Check navigation property names (must be exact, case-sensitive)
- Check field names in $select (must exist in that entity)
- Use the metadata discovery scripts to verify names

---

## Key Learnings

1. **Navigation Properties are Case-Sensitive:**
   - ✅ `crca7_ExistingContact`
   - ❌ `existingcontact`

2. **Field Names Vary by Entity:**
   - Contact: `gendercode` not `aha_gender`
   - Contact: `crca7_age` not `aha_age`

3. **Formatted Values are Critical:**
   - Without Prefer header: `statuscode: 1`
   - With Prefer header: `statuscode: "Paid"`

4. **Nested Expands are Powerful:**
   - QR Codes → Event Guest → Existing Contact
   - Gets Contact ID through 2 levels of relationships

5. **Column Name Consistency:**
   - Must match EXACTLY what EventRegistrationProcessorV3 expects
   - Any mismatch causes "Missing required columns" error

---

## Next Steps (Optional Enhancements)

1. **Add $filter to API calls** to reduce data pulled (use view_id)
2. **Cache expanded metadata** to avoid repeated entity discovery
3. **Add progress indicators** for each entity pull
4. **Validate Contact ID uniqueness** before processing
5. **Add data preview** before final processing

---

**Last Updated:** 2026-01-12  
**Status:** ✅ Ready for Testing  
**Docker Image:** 570ef30663f5
