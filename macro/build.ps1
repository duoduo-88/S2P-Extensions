# Build S2P-Joystick-Macro.exe (portable, one file) with PyInstaller.
#   powershell -ExecutionPolicy Bypass -File macro\build.ps1
# Requires: Python 3.11+ with PyInstaller (pip install pyinstaller).
param(
    [string]$Python = "python",
    [switch]$SkipTests  # scripts\package_release.ps1 already ran them
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$macro = Join-Path $repo "macro"
$sdk = Join-Path $repo "sdk"
$out = Join-Path $repo "dist\S2P-Joystick-Macro"
$work = Join-Path $repo "build\S2P-Joystick-Macro"

if (-not $SkipTests) {
    & $Python -m unittest discover -s (Join-Path $repo "tests")
    if ($LASTEXITCODE -ne 0) { throw "Tests failed; not building." }
}

& $Python -m PyInstaller `
    --noconfirm --clean --onefile --windowed `
    --name "S2P-Joystick-Macro" `
    --icon (Join-Path $macro "s2p_macro\assets\icon.ico") `
    --add-data "$(Join-Path $macro 's2p_macro\assets');s2p_macro\assets" `
    --paths $sdk --paths $macro `
    --distpath $out --workpath $work --specpath $work `
    (Join-Path $macro "s2p_macro\__main__.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

Copy-Item (Join-Path $repo "macro\README.md") $out -Force
Copy-Item (Join-Path $repo "macro\README_zh-TW.md") $out -Force
# S2P reads this manifest next to the EXE for Check for Updates.
& $Python (Join-Path $repo "scripts\tool_manifest.py") manifest "S2P-Joystick-Macro" `
    (Join-Path $macro "s2p_macro\__init__.py") $out
if ($LASTEXITCODE -ne 0) { throw "Could not write the tool manifest." }
Write-Host "Built $out\S2P-Joystick-Macro.exe"
Write-Host "Add this EXE to S2P-XInput-Lite > Extensions to let it connect."
