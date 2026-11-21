# Build a single-file Windows desktop executable (no console window).
# Usage: powershell -ExecutionPolicy Bypass -File build\build_exe.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

Write-Host '[1/3] generating icon'
python tools\make_icon.py

Write-Host '[2/3] cleaning old output'
Remove-Item -Recurse -Force "$root\build\pyinstaller" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$root\dist" -ErrorAction SilentlyContinue

Write-Host '[3/3] pyinstaller build'
python -m PyInstaller `
  --noconfirm --clean --onefile --windowed `
  --name JDScope `
  --icon "$root\assets\icon.ico" `
  --add-data "$root\app\web;app/web" `
  --add-data "$root\assets\icon.ico;assets" `
  --hidden-import webview.platforms.winforms `
  --hidden-import webview.platforms.edgechromium `
  --hidden-import clr_loader `
  --collect-submodules webview `
  --distpath "$root\dist" `
  --workpath "$root\build\pyinstaller" `
  --specpath "$root\build" `
  "$root\run.py"

Write-Host ''
Write-Host ('done: ' + (Join-Path $root 'dist\JDScope.exe'))
