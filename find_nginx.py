import subprocess

# Find which nginx process is the master (parent of workers)
r = subprocess.run('wmic process where "name=\'nginx.exe\'" get processid,parentprocessid',
                    shell=True, capture_output=True, text=True)
print("Nginx processes:")
print(r.stdout)

# Find the master (parent=0 or parent=itself)
lines = [l for l in r.stdout.strip().split('\n') if l.strip() and 'processid' not in l.lower()]
for line in lines:
    parts = line.strip().split()
    if len(parts) >= 2:
        pid = parts[0]
        parent = parts[1] if len(parts) > 1 else ''
        print(f"  PID={pid}, Parent={parent}")
