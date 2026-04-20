import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.environ.setdefault("EXTENSIONS_DB_HOST", "eai-flow-postgres-ext")
os.environ.setdefault("EXTENSIONS_DB_PORT", "5434")
os.environ.setdefault("EXTENSIONS_DB_USER", "eai_flow")
os.environ.setdefault("EXTENSIONS_DB_PASSWORD", "eai_flow_secure")
os.environ.setdefault("EXTENSIONS_DB_NAME", "eai_extensions")

from app.extensions.config import get_extensions_config
cfg = get_extensions_config()
print(f"DB URL: {cfg.database.url}")
print(f"DB Host: {cfg.database.host}:{cfg.database.port}")
print(f"DB Name: {cfg.database.name}")
print("Config loaded successfully!")
