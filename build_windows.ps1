$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$venv = Join-Path $projectRoot ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    py -3.12 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python 3.12 build environment." }
}

& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip in the build environment." }

& $python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Could not install the app or packaging dependencies." }

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name SpotLightApp `
    --icon "media\spotlight.ico" `
    --add-data "media:media" `
    --collect-all customtkinter `
    --distpath "dist" `
    --workpath "build\pyinstaller" `
    --specpath "build\spec" `
    "main.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller could not build SpotLightApp." }

Write-Host "Build complete: $projectRoot\dist\SpotLightApp\SpotLightApp.exe"
Write-Host "Next, open SpotLightApp.iss in Inno Setup Compiler and select Build > Compile."
