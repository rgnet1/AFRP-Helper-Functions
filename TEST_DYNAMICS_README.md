# Test Dynamics 365 Access

This script validates your Dynamics 365 CRM access configuration.

## Run Locally

```bash
python3 test_dynamics_access.py
```

## Run in Docker

```bash
# Option 1: Copy script into container and run
docker cp test_dynamics_access.py qr_code_generator_afrp-helper_1:/app/
docker exec -it qr_code_generator_afrp-helper_1 python3 /app/test_dynamics_access.py

# Option 2: Run directly (if volumes are mounted)
docker exec -it qr_code_generator_afrp-helper_1 python3 test_dynamics_access.py
```

## What the Script Tests

1. **Environment Variables** - Checks all required credentials are set
2. **OAuth Token** - Verifies authentication with Azure AD
3. **API Connectivity** - Tests basic connection with WhoAmI endpoint
4. **Entity Access** - Tests access to all 4 required entities:
   - Event Guests (crca7_eventguests)
   - QR Codes (aha_eventguestqrcodes)
   - Seating Tables (aha_seatingtables)
   - Form Responses (aha_eventformresponses)

## Expected Output

### ✅ If Working Correctly:
```
✓ OAuth token acquired successfully!
✓ API connectivity successful!
✓ Event Guests - Access granted!
✓ QR Codes - Access granted!
✓ Seating Tables - Access granted!
✓ Form Responses - Access granted!

ALL TESTS PASSED (4/4)
```

### ❌ If Application User Not Created:
```
✓ OAuth token acquired successfully!
✗ 403 FORBIDDEN - No access to this entity
⚠ This means the Application User needs permissions

ALL TESTS FAILED (0/4)
```

## Troubleshooting

- **403 Errors**: Application User not created → See `DYNAMICS_403_TROUBLESHOOTING.md`
- **404 Errors**: Entity name might be wrong (singular vs plural)
- **Token Errors**: Check Azure AD app registration and client secret
