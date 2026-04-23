# Stop frontend dev server on port 4000
$procIds = Get-NetTCPConnection -LocalPort 4000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($proc in $procIds) {
    Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped process $proc on port 4000"
}
if ($null -eq $procIds -or $procIds.Count -eq 0) {
    Write-Host "No process found on port 4000"
}
