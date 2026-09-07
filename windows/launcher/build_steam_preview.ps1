$ErrorActionPreference = 'Stop'
Push-Location (Join-Path $PSScriptRoot '../..')
try {
    python -m PyInstaller --noconfirm --clean --windowed --paths shared/python --collect-all drowned_shared --name Drowned-Launcher-Steam-Preview windows/launcher/app_steam.py
    if ($LASTEXITCODE -ne 0) { throw 'Launcher preview build failed.' }
    Write-Host 'Ready: dist/Drowned-Launcher-Steam-Preview/Drowned-Launcher-Steam-Preview.exe'
} finally {
    Pop-Location
}
