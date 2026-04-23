# Restart frontend dev server
Set-Location "d:\eai\eai-flow-main\frontend"
$env:PORT = "4000"
Write-Host "Starting frontend dev server on port 4000..."
Start-Process powershell.exe -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","D:\eai\eai-flow-main\scripts\frontend-startup.ps1","-Mode","dev" -WindowStyle Normal
Write-Host "Frontend dev server started."
