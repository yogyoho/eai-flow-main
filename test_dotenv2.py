"""Deep .env diagnostic."""
from pathlib import Path
from dotenv import dotenv_values
import os

env_path = Path(__file__).parent / ".env"
print(f"File: {env_path}")
print(f"Exists: {env_path.exists()}")
print(f"Size: {env_path.stat().st_size} bytes")

# Read raw bytes
raw = env_path.read_bytes()
print(f"\nFirst 200 bytes (hex):")
print(raw[:200].hex())

# Try different dotenv approaches
print("\n--- dotenv_values() ---")
vals = dotenv_values(env_path)
for k in ['EXTENSIONS_DB_USER', 'EXTENSIONS_DB_NAME', 'EXTENSIONS_DB_PASSWORD']:
    print(f"  {k}={vals.get(k)!r}")

print("\n--- load_dotenv() then os.getenv() ---")
from dotenv import load_dotenv
load_dotenv(env_path, override=True)
for k in ['EXTENSIONS_DB_USER', 'EXTENSIONS_DB_NAME', 'EXTENSIONS_DB_PASSWORD']:
    print(f"  {k}={os.getenv(k)!r}")

# Read the file manually
print("\n--- Manual line-by-line ---")
for line in env_path.read_text(encoding='utf-8').splitlines():
    if 'EXTENSIONS' in line and not line.strip().startswith('#'):
        print(f"  {line!r}")
