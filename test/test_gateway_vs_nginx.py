import urllib.request

tests = [
    ('gateway', 'http://localhost:4001'),
    ('nginx', 'http://localhost:4026'),
]

for name, base in tests:
    print(f"\n=== {name} ===")
    for path in ['/api/extensions/knowledge-bases', '/api/extensions/departments', '/api/extensions/docmgr/folders']:
        url = base + path
        req = urllib.request.Request(url)
        try:
            resp = urllib.request.urlopen(req, timeout=5)
            print(f"  [200] {path}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"  [{e.code}] {path}: {body[:100]}")
        except Exception as e:
            print(f"  [ERR] {path}: {type(e).__name__}: {e}")
