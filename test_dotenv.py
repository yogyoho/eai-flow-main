"""Test .env loading."""
from pathlib import Path
from dotenv import load_dotenv
import os

# Test 1: Current directory
print(f"cwd: {os.getcwd()}")

# Test 2: .env from project root
_env1 = Path(__file__).parent / ".env"
print(f"\nTest 1 - Path(__file__).parent: {_env1}")
print(f"  Exists: {_env1.exists()}")
load_dotenv(_env1)
print(f"  EXTENSIONS_DB_USER: {os.getenv('EXTENSIONS_DB_USER')}")
print(f"  EXTENSIONS_DB_NAME: {os.getenv('EXTENSIONS_DB_NAME')}")

# Test 3: .env from different locations
for p in [
    Path(__file__).parent / ".env",
    Path("d:/eai/eai-flow-main/.env"),
    Path(".") / ".env",
]:
    print(f"\n  Trying: {p} -> exists={p.exists()}")
