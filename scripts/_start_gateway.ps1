$ErrorActionPreference = "Continue"
$env:PYTHONPATH = "D:\eai\eai-flow-main\backend"
$env:RAGFLOW_BASE_URL = "http://localhost:9380"
$env:RAGFLOW_API_KEY = "ragflow-E6EpAHF_S3PKiNmp1pELAky4dXJNy0vLjWYTFhdNk28"
$env:RAGFLOW_TIMEOUT = "30"

Set-Location "D:\eai\eai-flow-main\backend"
& "C:\Python314\Scripts\uv.exe" run python -m uvicorn app.gateway.app:app --host 0.0.0.0 --port 4001 --log-level info
