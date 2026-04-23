# Verify frontend is responding
try {
    $response = Invoke-WebRequest -Uri "http://localhost:4000" -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($response.StatusCode) {
        Write-Host "Frontend is responding with status code: $($response.StatusCode)"
    }
} catch {
    Write-Host "Frontend may still be starting or not yet responding: $_"
}
$procIds = Get-NetTCPConnection -LocalPort 4000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($proc in $procIds) {
    $procName = (Get-Process -Id $proc -ErrorAction SilentlyContinue).ProcessName
    Write-Host "Process on port 4000: PID=$proc ($procName)"
}
