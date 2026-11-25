# Build a single-file Windows desktop executable (no console window).
# Usage: powershell -ExecutionPolicy Bypass -File build\build_exe.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$python = if ($env:JDSCOPE_PYTHON) { $env:JDSCOPE_PYTHON } else { 'python' }
$pyinstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue

Write-Host '[1/4] generating icon'
if (Test-Path "$root\assets\icon-src.png") {
  # Source artwork available: crop, make corners transparent, emit 7 sizes.
  # Needs Pillow (icon conversion only, not a runtime dependency).
  & $python tools\png_to_ico.py
} else {
  # Fallback: draw the icon from scratch with the standard library only.
  & $python tools\make_icon.py
}
if ($LASTEXITCODE -ne 0) { throw 'icon generation failed' }

Write-Host '[2/4] cleaning old output'
Remove-Item -Recurse -Force "$root\build\pyinstaller" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$root\dist" -ErrorAction SilentlyContinue

Write-Host '[3/4] pyinstaller build'
$buildArgs = @(
  '--noconfirm', '--clean', '--onefile', '--windowed',
  '--name', 'JDScope',
  '--icon', "$root\assets\icon.ico",
  '--add-data', "$root\app\web;app/web",
  '--add-data', "$root\assets\icon.ico;assets",
  '--hidden-import', 'webview.platforms.winforms',
  '--hidden-import', 'webview.platforms.edgechromium',
  '--hidden-import', 'clr_loader',
  '--collect-submodules', 'webview',
  '--distpath', "$root\dist",
  '--workpath', "$root\build\pyinstaller",
  '--specpath', "$root\build",
  "$root\run.py"
)
if ($pyinstaller) {
  & $pyinstaller.Source @buildArgs
} else {
  & $python -m PyInstaller @buildArgs
}
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }

Write-Host '[4/4] refreshing desktop shortcut'
& "$root\build\create_shortcut.ps1"

Write-Host ''
Write-Host ('done: ' + (Join-Path $root 'dist\JDScope.exe'))
