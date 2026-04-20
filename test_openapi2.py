import urllib.request
import json

base = 'http://localhost:4001'
url = base + '/openapi.json'
req = urllib.request.Request(url)
try:
    resp = urllib.request.urlopen(req, timeout=5)
    data = json.loads(resp.read())
    paths = list(data.get('paths', {}).keys())
    # Show only extension paths
    ext_paths = [p for p in paths if 'extensions' in p]
    print(f"Gateway version from openapi: {data.get('info', {}).get('version', 'unknown')}")
    print(f"\nExtension paths ({len(ext_paths)}):")
    for p in sorted(ext_paths):
        print(f"  {p}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    # Try to get server header
    import http.client
    conn = http.client.HTTPConnection('localhost', 4001, timeout=5)
    try:
        conn.request('GET', '/')
        r = conn.getresponse()
        print(f"Server responded: {r.status} {r.reason}")
        print(f"Headers: {dict(r.getheaders())}")
    except Exception as e2:
        print(f"Also failed to connect: {type(e2).__name__}: {e2}")
    finally:
        conn.close()
