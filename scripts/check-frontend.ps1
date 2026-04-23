$procIds = Get-NetTCPConnection -LocalPort 4000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
if ($procIds) {
    foreach ($proc in $procIds) {
        $procName = (Get-Process -Id $proc -ErrorAction SilentlyContinue).ProcessName
        Write-Host "Port 4000 is in use by PID: $proc ($procName)"
    }
} else {
    Write-Host "Port 4000 is not in use"
}
