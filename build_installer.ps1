$ErrorActionPreference = "Stop"

.\build_exe.ps1

$innoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)

$iscc = $innoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup was not found."
    Write-Host "Install Inno Setup 6, then run this script again:"
    Write-Host "https://jrsoftware.org/isinfo.php"
    exit 1
}

Write-Host "Building Windows installer..."
& $iscc "installer\SmartFileOrganizer.iss"

Write-Host ""
Write-Host "Done. Your installer is here:"
Write-Host "outputs\SmartFileOrganizerSetup.exe"
