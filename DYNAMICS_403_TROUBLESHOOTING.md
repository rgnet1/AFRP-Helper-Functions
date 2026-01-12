# Dynamics CRM 403 Forbidden Error - Troubleshooting Guide

## Error
```
Failed to pull Event Guests: 403 Client Error: Forbidden for url: 
https://afrp.crm.dynamics.com/api/data/v9.2/crca7_eventguests
```

## Root Cause
The Azure AD application is not registered as an **Application User** in Dynamics 365, or doesn't have the necessary security roles assigned.

## Critical Fix Required: Create Application User in Dynamics 365

### Step 1: Register Application User in Dynamics 365
You MUST create an Application User in Dynamics 365 and assign it security roles:

1. **Go to Dynamics 365** (https://afrp.crm.dynamics.com)
2. Navigate to **Settings** → **Security** → **Users**
3. Change view to **Application Users**
4. Click **+ New**
5. Fill in the form:
   - **User Name**: Something like `badge-generator-v2@afrp.onmicrosoft.com`
   - **Application ID**: `522f5389-743b-438c-95a7-7fa891958455` (your Client ID)
   - **Full Name**: Badge Generator V2 Service
   - **Primary Email**: your-admin-email@afrp.org
6. Click **Save**
7. **Assign Security Roles**: Click "Manage Roles" and assign:
   - **System Administrator** (for testing - can narrow down later)
   - Or at minimum: roles that have Read access to:
     - Event Guests (crca7_eventguest)
     - QR Codes (aha_eventguestqrcodes)
     - Seating Tables (aha_seatingtable)
     - Form Responses (aha_eventformresponses)

### Step 2: Verify Azure AD App Registration
### Step 2: Verify Azure AD App Registration
1. Go to Azure Portal (https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App Registrations**
3. Find your app (Client ID: `522f5389-743b-438c-95a7-7fa891958455`)
4. Go to **API Permissions**
5. Ensure you have:
   - **Dynamics CRM** → `user_impersonation` (Delegated) - NOT needed for service principal
   - **Dynamics CRM / Dataverse** → API permissions
6. Click **"Grant admin consent"** for your tenant
7. Wait 5-10 minutes for changes to propagate

### Step 3: Verify Client Secret is Valid
1. In the same App Registration
2. Go to **Certificates & secrets**
3. Check that your client secret hasn't expired
4. If expired, create a new one and update `config/.env`

## Important: Application User vs User Authentication

Your app is using **Service Principal** (application) authentication, which requires:
- ✅ Application User created in Dynamics 365
- ✅ Security roles assigned to that Application User
- ✅ Valid OAuth token with correct scope

**This is NOT the same as** user delegation - you don't need a real user to sign in.

## Alternative Fix: Check Entity Plural Names

Dynamics 365 entity names might be pluralized differently. Try these variations:

### Current Names (may be wrong):
- `crca7_eventguests` 
- `aha_eventguestqrcodes`
- `aha_seatingtable` 
- `aha_eventformresponses`

### Try These Instead:
```python
# Singular forms:
"crca7_eventguest"  # no 's'
"aha_eventguestqrcode"  # no 's'
"aha_seatingtable"  # already singular
"aha_eventformresponse"  # no 's'
```

## Testing Steps
```python
# Instead of:
endpoint = f"crca7_eventguests?savedQuery={view_id}"

# Now uses:
endpoint = f"crca7_eventguests"
```

**Note:** This fetches ALL records, not just those in the view. You may need to:
- Add `$filter` queries to limit data
- Add `$top` to limit record count
- Process filtering on the server side

### Option 3: Fix Entity Names
The table reservation entity might be named differently:
- Try: `aha_seatingtable` (singular)
- Or: `aha_seatingtables` (plural)
- Or: `aha_tablereservations`

Check your Dynamics CRM to verify the exact entity logical names.

## Testing the Fix

1. **Test basic access** (without savedQuery):
```bash
# From inside the container
docker exec -it qr_code_generator_afrp-helper_1 python3 << 'EOF'
from utils.dynamics_crm import DynamicsCRMClient
client = DynamicsCRMClient()
df = client.get_event_guests("")
print(f"Fetched {len(df)} event guests")
print(df.columns.tolist())
EOF
```

2. **Check OAuth token**:
```bash
# Verify the token is being obtained
docker logs qr_code_generator_afrp-helper_1 2>&1 | grep -i "dynamics\|auth\|token"
```

3. **Test from Badge Generator V2**:
   - Go to http://localhost:5066/badges-v2
   - Select "Convention 2025" config
   - Select an event
   - Click "Pull All & Process"
   - Check browser console for error details

## Alternative: Use FetchXML with SavedQuery

If you need to respect the saved query filters, you'll need to:

1. Fetch the savedquery definition:
```python
endpoint = f"savedqueries({view_id})?$select=fetchxml"
response = self._make_request(endpoint)
fetchxml = response['fetchxml']
```

2. Execute the FetchXML:
```python
endpoint = f"crca7_eventguests?fetchXml={urllib.parse.quote(fetchxml)}"
response = self._make_request(endpoint)
```

This requires additional OAuth permissions for accessing `savedqueries` entity.

## Current Status
- ✅ OAuth authentication working (token obtained)
- ✅ Connection to Dynamics CRM established
- ❌ savedQuery parameter not authorized
- ✅ Workaround: Fetch all records (no filtering)

## Next Steps
1. Contact your Azure AD admin to grant API permissions
2. Or adjust the code to add `$filter` queries for data filtering
3. Test with the updated permissions

## Finding Correct Entity Names (404 Errors)

If you're getting 404 errors, you might be using the wrong entity name. Dynamics 365 Web API uses **EntitySetName** (the collection name), not the **LogicalName**.

### Quick Discovery Script

Save this as `discover_entities.py` and run it to find the correct entity names:

```python
import os
import msal
import requests
from dotenv import load_dotenv

# Load config
load_dotenv('config/.env')

tenant_id = os.getenv('DYNAMICS_TENANT_ID')
client_id = os.getenv('DYNAMICS_CLIENT_ID')
client_secret = os.getenv('DYNAMICS_CLIENT_SECRET')
crm_url = os.getenv('DYNAMICS_CRM_URL')

# Get token
app = msal.ConfidentialClientApplication(
    client_id=client_id,
    authority=f"https://login.microsoftonline.com/{tenant_id}",
    client_credential=client_secret
)
result = app.acquire_token_for_client(scopes=[f"{crm_url}/.default"])
token = result["access_token"]

# Query EntityDefinitions for EntitySetName
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

url = f"{crm_url}/api/data/v9.2/EntityDefinitions?$select=LogicalName,EntitySetName&$filter=IsCustomEntity eq true"
response = requests.get(url, headers=headers)

entities = response.json().get('value', [])
for entity in entities:
    if 'qr' in entity['LogicalName'] or 'form' in entity['LogicalName']:
        print(f"{entity['LogicalName']} → {entity['EntitySetName']}")
```

### Correct Entity Names for Badge Generator V2

| Display Name | Logical Name | EntitySetName (USE THIS!) |
|--------------|--------------|---------------------------|
| Event Guests | crca7_eventguest | **crca7_eventguests** |
| QR Codes | aha_eventguestqrcodes | **aha_eventguestqrcodeses** |
| Seating Tables | aha_seatingtable | **aha_seatingtables** |
| Form Responses | aha_eventformresponses | **aha_eventformresponseses** |

**Note**: Some entities have unusual pluralization (e.g., `qrcodeses` with double 'es'). Always use the EntitySetName from the API!
