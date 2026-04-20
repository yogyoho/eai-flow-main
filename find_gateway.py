import psutil
import os

for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline', 'cwd']):
    try:
        if 'python' in proc.info['name'].lower():
            cmdline = proc.info['cmdline']
            if cmdline and any('uvicorn' in str(c) or 'gateway' in str(c) or 'langgraph' in str(c) for c in cmdline):
                print(f"PID: {proc.info['pid']}")
                print(f"Name: {proc.info['name']}")
                print(f"CWD: {proc.info['cwd']}")
                print(f"CmdLine: {' '.join(cmdline)}")
                env = proc.environ()
                if 'DEER_FLOW_CONFIG_PATH' in env:
                    print(f"DEER_FLOW_CONFIG_PATH: {env.get('DEER_FLOW_CONFIG_PATH')}")
                else:
                    print("DEER_FLOW_CONFIG_PATH: (not set)")
                print("---")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
