"""Simple gateway launcher."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

print("ENV loaded:")
print(f"  EXTENSIONS_DB_USER={os.getenv('EXTENSIONS_DB_USER')}")
print(f"  EXTENSIONS_DB_NAME={os.getenv('EXTENSIONS_DB_NAME')}")

os.chdir(str(Path(__file__).parent))
os.environ["PYTHONPATH"] = str(Path(__file__).parent)

print("Starting uvicorn...")
os.execv(sys.executable, [sys.executable, "-m", "uvicorn", "app.gateway.app:app", "--host", "0.0.0.0", "--port", "4001"])
