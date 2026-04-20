import urllib.request
import json

url = 'http://localhost:4001/auth/login'
data = json.dumps({'username': 'admin', 'password': 'admin123'}).encode()
headers = {'Content-Type': 'application/json'}

req = urllib.request.Request(url, data=data, headers=headers, method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=10)
    print(f"Status: {resp.status}")
    print(f"Body: {resp.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code}")
    print(f"Body: {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
