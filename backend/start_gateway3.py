"""Start gateway using backend venv uvicorn."""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

print(f"DB_USER={os.getenv('EXTENSIONS_DB_USER')}")
print(f"DB_NAME={os.getenv('EXTENSIONS_DB_NAME')}")

uvicorn = Path(__file__).parent / ".venv" / "Scripts" / "uvicorn.exe"
sys.path.insert(0, str(Path(__file__).parent))

os.chdir(str(Path(__file__).parent))
os.execv(str(uvicorn), [
    str(uvicorn),
    "app.gateway.app:app",
    "--host", "0.0.0.0",
    "--port", "4001",
    "--reload",
    "--reload-include=*.yaml",
    "--reload-include=.env",
    "--reload-exclude=*.pyc",
    "--reload-exclude=__pycache__",
])
