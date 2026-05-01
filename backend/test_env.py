# Test env loading
import sys

sys.path.insert(0, r"D:\eai\eai-flow-main\backend")
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(r"D:\eai\eai-flow-main\.env"), override=True)
import os

print("DB_USER:", os.getenv("EXTENSIONS_DB_USER"))
print("DB_NAME:", os.getenv("EXTENSIONS_DB_NAME"))
