# Create a desktop shortcut with the app icon.
# Usage: powershell -ExecutionPolicy Bypass -File build\create_shortcut.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$exe = Join-Path $root 'dist\JDScope.exe'
if (-not (Test-Path $exe)) {
    Write-Host 'dist\JDScope.exe not found. Run build\build_exe.ps1 first.'
    exit 1
}

$desktop = [Environment]::GetFolderPath('Desktop')
$link = Join-Path $desktop 'JDScope.lnk'
$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($link)
$sc.TargetPath = $exe
$sc.WorkingDirectory = (Split-Path $exe -Parent)
# The icon is embedded in the exe, so the shortcut stays valid if the folder moves.
$sc.IconLocation = "$exe,0"
$sc.Description = 'JDScope - JD insight and resume gap ledger'
$sc.Save()

Write-Host ('shortcut created: ' + $link)
