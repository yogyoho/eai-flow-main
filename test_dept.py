import urllib.request
import http.client
import json

base = 'http://localhost:4001'

# Test departments directly
url = base + '/api/extensions/departments'
req = urllib.request.Request(url, method='GET')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    body = resp.read().decode()
    print(f"[200] /api/extensions/departments: {body[:200]}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"[{e.code}] /api/extensions/departments: {body[:300]}")
except Exception as e:
    print(f"[ERR] /api/extensions/departments: {type(e).__name__}: {e}")

# Also test docmgr
url = base + '/api/extensions/docmgr/folders'
req = urllib.request.Request(url, method='GET')
try:
    resp = urllib.request.urlopen(req, timeout=5)
    body = resp.read().decode()
    print(f"[200] /api/extensions/docmgr/folders: {body[:200]}")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"[{e.code}] /api/extensions/docmgr/folders: {body[:300]}")
except Exception as e:
    print(f"[ERR] /api/extensions/docmgr/folders: {type(e).__name__}: {e}")
