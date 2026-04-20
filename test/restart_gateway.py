import os
import signal
import subprocess
import time
import sys

# Kill all processes on port 4001
result = subprocess.run('netstat -ano | findstr :4001 | findstr LISTENING',
                       shell=True, capture_output=True, text=True)
print(f"netstat output: {result.stdout}")

pids = []
for line in result.stdout.strip().split('\n'):
    if line:
        parts = line.split()
        if len(parts) >= 5:
            pid = int(parts[-1])
            pids.append(pid)

print(f"Found PIDs: {pids}")

for pid in pids:
    if pid not in (os.getpid(),):
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Killed PID {pid}")
        except Exception as e:
            print(f"Failed to kill {pid}: {e}")

time.sleep(2)

# Start new gateway
venv_python = r'D:\eai\eai-flow-main\backend\.venv\Scripts\python.exe'
uvicorn_exe = r'D:\eai\eai-flow-main\backend\.venv\Scripts\uvicorn.exe'
os.chdir(r'D:\eai\eai-flow-main\backend')

cmd = [
    uvicorn_exe,
    'app.gateway.app:app',
    '--host', '0.0.0.0',
    '--port', '4001',
    '--reload',
]
print(f"Starting: {' '.join(cmd)}")
proc = subprocess.Popen(cmd, cwd=r'D:\eai\eai-flow-main\backend')
print(f"Started gateway with PID {proc.pid}")
