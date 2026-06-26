$ErrorActionPreference = "Stop"

Write-Host "Installing project dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Host "Cleaning previous builds..."
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }

Write-Host "Building SmartFileOrganizer.exe..."
python -m PyInstaller SmartFileOrganizer.spec --clean --noconfirm

Write-Host ""
Write-Host "Done. Your executable is here:"
Write-Host "dist\SmartFileOrganizer.exe"
