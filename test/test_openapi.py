import urllib.request
import json

base = 'http://localhost:4001'

# Get OpenAPI schema to verify routes
req = urllib.request.Request(base + '/openapi.json')
resp = urllib.request.urlopen(req, timeout=5)
data = json.loads(resp.read())

paths = list(data.get('paths', {}).keys())
print("All paths:")
for p in sorted(paths):
    print(f"  {p}")

print("\nChecking extension paths:")
for p in sorted(paths):
    if 'extensions' in p or 'departments' in p or 'docmgr' in p:
        print(f"  {p}")
