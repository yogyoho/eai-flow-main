# Frontend development startup script for Windows
# Called by serve.sh via PowerShell to avoid MSYS2 bash + "Program Files" path issues
param(
    [string]$Mode = "dev",
    [string]$Secret = ""
)

$ErrorActionPreference = "Continue"
Set-Location "d:\eai\eai-flow-main\frontend"

if ($Mode -eq "dev") {
    $env:PORT = "4000"
    pnpm run dev
} else {
    $env:BETTER_AUTH_SECRET = $Secret
    $env:PORT = "4000"
    pnpm run preview
}
