import subprocess
import time
import urllib.request
import json

# Start gateway on port 4002
uvicorn_exe = r'D:\eai\eai-flow-main\backend\.venv\Scripts\uvicorn.exe'
proc = subprocess.Popen(
    [uvicorn_exe, 'app.gateway.app:app', '--host', '0.0.0.0', '--port', '4002', '--reload'],
    cwd=r'D:\eai\eai-flow-main\backend',
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
print(f"Started gateway on 4002 with PID {proc.pid}")

# Wait for startup
time.sleep(6)

# Test it
try:
    req = urllib.request.Request('http://localhost:4002/openapi.json')
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    paths = list(data.get('paths', {}).keys())
    dept_paths = [p for p in paths if 'departments' in p and 'user' not in p]
    docmgr_paths = [p for p in paths if 'docmgr' in p]
    print(f"\nTotal paths: {len(paths)}")
    print(f"Departments (non-user): {dept_paths}")
    print(f"Docmgr: {docmgr_paths}")
    
    for ep in ['/api/extensions/departments', '/api/extensions/docmgr/folders']:
        req2 = urllib.request.Request(f'http://localhost:4002{ep}')
        try:
            r = urllib.request.urlopen(req2, timeout=5)
            print(f"[200] {ep}: {r.read().decode()[:200]}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"[{e.code}] {ep}: {body[:200]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
