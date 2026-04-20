import urllib.request
import json
import sys

# Test 1: Health check
print("=== Test 1: Health Check ===")
try:
    resp = urllib.request.urlopen('http://localhost:4001/health', timeout=3)
    print(f"Status: {resp.status}")
    print(f"Body: {resp.read().decode()}")
except Exception as e:
    print(f"Error: {e}")

print()

# Test 2: Login
print("=== Test 2: Login ===")
req = urllib.request.Request(
    'http://localhost:4001/auth/login',
    data=json.dumps({'username': 'admin', 'password': 'admin123'}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST'
)
try:
    resp = urllib.request.urlopen(req, timeout=5)
    print(f"Status: {resp.status}")
    print(f"Body: {resp.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    body = e.read().decode()
    print(f"Body: {body}")
    print(f"Headers: {dict(e.headers)}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

print()

# Test 3: OpenAPI schema
print("=== Test 3: OpenAPI ===")
try:
    resp = urllib.request.urlopen('http://localhost:4001/openapi.json', timeout=3)
    data = json.loads(resp.read().decode())
    paths = list(data.get('paths', {}).keys())
    print(f"Available paths: {paths}")
    # Check for auth paths
    auth_paths = [p for p in paths if 'auth' in p.lower()]
    print(f"Auth paths: {auth_paths}")
except Exception as e:
    print(f"Error: {e}")
