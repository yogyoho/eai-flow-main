import subprocess
import time
import sys

# Start gateway on port 4002
venv_python = r'D:\eai\eai-flow-main\backend\.venv\Scripts\python.exe'
uvicorn_exe = r'D:\eai\eai-flow-main\backend\.venv\Scripts\uvicorn.exe'

cmd = [
    uvicorn_exe,
    'app.gateway.app:app',
    '--host', '0.0.0.0',
    '--port', '4002',
    '--reload',
]
print(f"Starting: {' '.join(cmd)}")
proc = subprocess.Popen(cmd, cwd=r'D:\eai\eai-flow-main\backend', 
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print(f"Started gateway with PID {proc.pid}")

# Wait for startup
time.sleep(5)

# Test
import urllib.request
try:
    url = 'http://localhost:4002/openapi.json'
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req, timeout=10)
    import json
    data = json.loads(resp.read())
    paths = list(data.get('paths', {}).keys())
    dept_paths = [p for p in paths if 'departments' in p and 'user' not in p]
    docmgr_paths = [p for p in paths if 'docmgr' in p]
    print(f"\nTotal paths: {len(paths)}")
    print(f"Departments (non-user): {dept_paths}")
    print(f"Docmgr: {docmgr_paths}")
    
    # Test endpoints
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
    import traceback
    traceback.print_exc()
