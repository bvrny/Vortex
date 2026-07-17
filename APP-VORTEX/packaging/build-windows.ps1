# Build the Windows onefile distribution of the Vortex app.
# Run from APP-VORTEX\: .\packaging\build-windows.ps1
# Requires: pip install pyinstaller (inside the project venv).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

pyinstaller `
    --name vortex-app `
    --onefile `
    --windowed `
    --paths ..\PROTO-VORTEX-01A\generated `
    --hidden-import vortex_protocol `
    --noconfirm `
    vortex_app\__main__.py

Write-Host "dist\vortex-app.exe ready."
