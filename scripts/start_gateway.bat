@echo off
setlocal
cd /d D:\eai\eai-flow-main\backend
set PYTHONPATH=D:\eai\eai-flow-main\backend
start "" /b python -c "import asyncio; from app.extensions.database import init_db; asyncio.run(init_db())" 2>nul
uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 4001 --reload --reload-include="*.yaml" --reload-include=".env" --reload-exclude="*.pyc" --reload-exclude="__pycache__" --reload-exclude="sandbox/" --reload-exclude=".deer-flow/" > D:\eai\eai-flow-main\logs\gateway_new.log 2>&1
endlocal
