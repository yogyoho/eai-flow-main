@echo off
setlocal
cd /d D:\eai\eai-flow-main\backend
set PYTHONPATH=.
"C:\Python314\Scripts\uv.exe" run uvicorn app.gateway.app:app --host 0.0.0.0 --port 4001 --no-reload > ..\logs\gateway.log 2>&1
endlocal
