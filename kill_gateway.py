import subprocess
import time

# Kill all processes on port 4001
r = subprocess.run('netstat -ano | findstr :4001 | findstr LISTENING',
                   shell=True, capture_output=True, text=True)
print("Current listeners:", r.stdout)

pids = set()
for line in r.stdout.strip().split('\n'):
    parts = line.split()
    if len(parts) >= 5:
        pids.add(int(parts[-1]))

print(f"PIDs to kill: {pids}")
for pid in pids:
    r2 = subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True, text=True)
    print(f"Kill {pid}: returncode={r2.returncode} stdout={r2.stdout.strip()} stderr={r2.stderr.strip() if r2.stderr else ''}")

time.sleep(3)

# Check if port is free
r3 = subprocess.run('netstat -ano | findstr :4001 | findstr LISTENING',
                    shell=True, capture_output=True, text=True)
print(f"After kill: {r3.stdout.strip() or 'PORT IS FREE'}")
