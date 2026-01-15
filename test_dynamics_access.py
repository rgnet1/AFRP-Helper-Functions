#!/usr/bin/env python3
"""
Dynamics 365 CRM Access Validation Test
Tests OAuth authentication and API access to validate Application User setup.
"""

import os
import sys
import json
from datetime import datetime
import msal
import requests
from dotenv import load_dotenv

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Colors.GREEN}✓{Colors.END} {msg}")

def print_error(msg):
    print(f"{Colors.RED}✗{Colors.END} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠{Colors.END} {msg}")

def print_info(msg):
    print(f"{Colors.BLUE}ℹ{Colors.END} {msg}")

def print_header(msg):
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.END}")
    print(f"{Colors.BOLD}{msg}{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.END}\n")

# Load environment variables
IN_DOCKER = os.environ.get('DOCKER_CONTAINER', False)
BASE_PATH = '/app' if IN_DOCKER else '.'
CONFIG_PATH = '/config' if IN_DOCKER else f"{BASE_PATH}/config"
env_path = os.path.join(CONFIG_PATH, '.env')

print_header("Dynamics 365 CRM Access Validation Test")
print(f"Environment: {'Docker' if IN_DOCKER else 'Local'}")
print(f"Config Path: {CONFIG_PATH}")
print(f"Loading .env from: {env_path}")

if not os.path.exists(env_path):
    print_error(f".env file not found at: {env_path}")
    print_info("Please copy config/.env.sample to config/.env and fill in your credentials")
    sys.exit(1)

load_dotenv(env_path)

# Test 1: Check environment variables
print_header("Test 1: Checking Environment Variables")

tenant_id = os.getenv('DYNAMICS_TENANT_ID')
client_id = os.getenv('DYNAMICS_CLIENT_ID')
client_secret = os.getenv('DYNAMICS_CLIENT_SECRET')
crm_url = os.getenv('DYNAMICS_CRM_URL')

required_vars = {
    'DYNAMICS_TENANT_ID': tenant_id,
    'DYNAMICS_CLIENT_ID': client_id,
    'DYNAMICS_CLIENT_SECRET': client_secret,
    'DYNAMICS_CRM_URL': crm_url
}

all_vars_present = True
for var_name, var_value in required_vars.items():
    if var_value:
        # Mask sensitive values
        if 'SECRET' in var_name:
            display_value = f"{var_value[:8]}...{var_value[-4:]}" if len(var_value) > 12 else "***"
        else:
            display_value = var_value
        print_success(f"{var_name}: {display_value}")
    else:
        print_error(f"{var_name}: NOT SET")
        all_vars_present = False

if not all_vars_present:
    print_error("Missing required environment variables!")
    sys.exit(1)

# Test 2: OAuth Token Acquisition
print_header("Test 2: Acquiring OAuth Token")

try:
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=f"https://login.microsoftonline.com/{tenant_id}",
        client_credential=client_secret
    )
    
    scope = [f"{crm_url}/.default"]
    print_info(f"Requesting token with scope: {scope[0]}")
    
    result = app.acquire_token_for_client(scopes=scope)
    
    if "access_token" in result:
        token = result["access_token"]
        print_success("OAuth token acquired successfully!")
        print_info(f"Token (first 20 chars): {token[:20]}...")
        
        # Decode token info (without verification)
        import base64
        token_parts = token.split('.')
        if len(token_parts) >= 2:
            # Add padding if needed
            payload = token_parts[1]
            payload += '=' * (4 - len(payload) % 4)
            decoded = json.loads(base64.b64decode(payload))
            print_info(f"Token expires: {datetime.fromtimestamp(decoded.get('exp', 0))}")
            print_info(f"Token issued for: {decoded.get('aud', 'N/A')}")
    else:
        print_error("Failed to acquire token!")
        print_error(f"Error: {result.get('error', 'Unknown')}")
        print_error(f"Description: {result.get('error_description', 'N/A')}")
        sys.exit(1)
        
except Exception as e:
    print_error(f"Exception during token acquisition: {str(e)}")
    sys.exit(1)

# Test 3: Test API Connectivity
print_header("Test 3: Testing API Connectivity")

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json",
    "OData-MaxVersion": "4.0",
    "OData-Version": "4.0"
}

# Test basic API endpoint
try:
    test_url = f"{crm_url}/api/data/v9.2/WhoAmI"
    print_info(f"Testing WhoAmI endpoint: {test_url}")
    
    response = requests.get(test_url, headers=headers, timeout=10)
    
    if response.status_code == 200:
        whoami = response.json()
        print_success("API connectivity successful!")
        print_info(f"User ID: {whoami.get('UserId', 'N/A')}")
        print_info(f"Business Unit ID: {whoami.get('BusinessUnitId', 'N/A')}")
        print_info(f"Organization ID: {whoami.get('OrganizationId', 'N/A')}")
    else:
        print_error(f"WhoAmI failed with status {response.status_code}")
        print_error(f"Response: {response.text}")
        
except Exception as e:
    print_error(f"Exception during API connectivity test: {str(e)}")

# Test 4: Test Entity Access
print_header("Test 4: Testing Entity Access")

entities_to_test = [
    ("Event Guests", "crca7_eventguests"),
    ("QR Codes", "aha_eventguestqrcodeses"),
    ("Seating Tables", "aha_seatingtables"),
    ("Form Responses", "aha_eventformresponseses"),
]

print_info("Testing $top=1 to check access without fetching all data...\n")

results = []
for entity_name, entity_logical_name in entities_to_test:
    try:
        # Use $top=1 to only fetch one record
        test_url = f"{crm_url}/api/data/v9.2/{entity_logical_name}?$top=1"
        print_info(f"Testing: {entity_name} ({entity_logical_name})")
        
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            record_count = len(data.get('value', []))
            print_success(f"  Access granted! (Found {record_count} record in sample)")
            results.append((entity_name, "SUCCESS", response.status_code, record_count))
        elif response.status_code == 403:
            print_error(f"  403 FORBIDDEN - No access to this entity")
            print_warning(f"  This means the Application User needs permissions for {entity_name}")
            results.append((entity_name, "FORBIDDEN", response.status_code, 0))
        elif response.status_code == 404:
            print_error(f"  404 NOT FOUND - Entity name might be incorrect")
            print_warning(f"  Try: {entity_logical_name[:-1]} (without 's')")
            results.append((entity_name, "NOT FOUND", response.status_code, 0))
        else:
            print_error(f"  Status {response.status_code}: {response.text[:100]}")
            results.append((entity_name, "ERROR", response.status_code, 0))
            
    except Exception as e:
        print_error(f"  Exception: {str(e)}")
        results.append((entity_name, "EXCEPTION", 0, 0))
    
    print()  # Blank line between tests

# Summary
print_header("Test Summary")

success_count = sum(1 for r in results if r[1] == "SUCCESS")
total_count = len(results)

print(f"\n{'Entity':<25} {'Status':<15} {'HTTP':<10} {'Records'}")
print("-" * 60)
for entity_name, status, status_code, count in results:
    status_symbol = "✓" if status == "SUCCESS" else "✗"
    status_color = Colors.GREEN if status == "SUCCESS" else Colors.RED
    print(f"{entity_name:<25} {status_color}{status_symbol} {status:<13}{Colors.END} {status_code:<10} {count}")

print("\n" + "=" * 60)
if success_count == total_count:
    print_success(f"ALL TESTS PASSED ({success_count}/{total_count})")
    print_info("Your Dynamics 365 access is properly configured!")
elif success_count > 0:
    print_warning(f"PARTIAL SUCCESS ({success_count}/{total_count})")
    print_info("Some entities are accessible, others need permission fixes")
else:
    print_error(f"ALL TESTS FAILED ({success_count}/{total_count})")
    print_warning("\nMost likely issue: Application User not created in Dynamics 365")
    print_info("See DYNAMICS_403_TROUBLESHOOTING.md for detailed fix instructions")

print("\n" + "=" * 60 + "\n")

# Exit with appropriate code
sys.exit(0 if success_count == total_count else 1)
