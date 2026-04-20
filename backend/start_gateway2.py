"""Start gateway using backend venv uv."""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

print(f"DB_USER={os.getenv('EXTENSIONS_DB_USER')}")
print(f"DB_NAME={os.getenv('EXTENSIONS_DB_NAME')}")

venv_python = Path(__file__).parent / ".venv" / "Scripts" / "python.exe"
uv = Path(__file__).parent / ".venv" / "Scripts" / "uv.exe"

if not venv_python.exists():
    print("ERROR: venv not found at", venv_python)
    sys.exit(1)

os.execv(str(venv_python), [
    str(venv_python),
    "-c",
    "import sys; sys.path.insert(0, '.'); exec(open('.venv\\Scripts\\activate_this.py').read()) if Path('.venv\\Scripts\\activate_this.py').exists() else None; "
    "import uvicorn; uvicorn.run('app.gateway.app:app', host='0.0.0.0', port=4001, reload=True)"
])
