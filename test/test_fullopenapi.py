import urllib.request
import json

base = 'http://localhost:4001'

# Fetch full openapi and count departments/docmgr paths
url = base + '/openapi.json'
req = urllib.request.Request(url)
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
paths = list(data.get('paths', {}).keys())

dept_paths = [p for p in paths if 'departments' in p]
docmgr_paths = [p for p in paths if 'docmgr' in p]
kf_paths = [p for p in paths if '/kf/' in p]

print(f"Total paths: {len(paths)}")
print(f"Departments paths ({len(dept_paths)}): {dept_paths}")
print(f"Docmgr paths ({len(docmgr_paths)}): {docmgr_paths}")
print(f"KF paths count: {len(kf_paths)}")

# Also test the endpoints directly
for ep in ['/api/extensions/departments', '/api/extensions/docmgr/folders']:
    req2 = urllib.request.Request(base + ep)
    try:
        r = urllib.request.urlopen(req2, timeout=5)
        print(f"[200] {ep}: {r.read().decode()[:100]}")
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {ep}: {e.read().decode()[:100]}")
    except Exception as e:
        print(f"[ERR] {ep}: {e}")
