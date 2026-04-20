import urllib.request
import json

base = 'http://localhost:4001'

tests = [
    # Extension APIs (need auth)
    ('GET', '/api/extensions/auth/me'),
    ('GET', '/api/extensions/roles'),
    ('GET', '/api/extensions/users?limit=5'),
    ('GET', '/api/extensions/departments'),
    ('GET', '/api/extensions/knowledge-bases'),
    ('GET', '/api/extensions/docmgr/documents'),
    ('GET', '/api/extensions/docmgr/folders'),
    ('GET', '/api/extensions/kf/rules'),
    ('GET', '/api/extensions/kf/templates'),
    ('GET', '/api/extensions/kf/laws'),
    ('GET', '/api/extensions/web-scraper/providers'),
    # Legacy paths should now be 404
    ('GET', '/kf/rules'),
    ('GET', '/departments'),
]

for method, path in tests:
    url = base + path
    req = urllib.request.Request(url, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        print(f"[200] {method} {path}")
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {method} {path}")
    except Exception as e:
        print(f"[ERR] {method} {path} - {type(e).__name__}: {e}")
