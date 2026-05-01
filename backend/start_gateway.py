"""Start gateway with correct environment variables."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env with override to ensure correct values
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, override=True)

print(f"DB_USER: {os.getenv('EXTENSIONS_DB_USER')}")
print(f"DB_NAME: {os.getenv('EXTENSIONS_DB_NAME')}")

# Now launch uvicorn as subprocess with these env vars
import subprocess

# Get all env vars to pass
env = os.environ.copy()

result = subprocess.run(
    [sys.executable, "-m", "uvicorn", "app.gateway.app:app", "--host", "0.0.0.0", "--port", "4001", "--reload", "--reload-include=*.yaml", "--reload-include=.env", "--reload-exclude=*.pyc", "--reload-exclude=__pycache__"],
    cwd=str(Path(__file__).parent),
    env=env,
)
sys.exit(result.returncode)
