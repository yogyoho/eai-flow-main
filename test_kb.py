import urllib.request
import json

url = 'http://localhost:4001/api/extensions/knowledge-bases'
req = urllib.request.Request(url, method='GET')
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"Status: {resp.status}")
    print(f"Body: {resp.read().decode()[:500]}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    body = e.read().decode()
    print(f"Body: {body}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
