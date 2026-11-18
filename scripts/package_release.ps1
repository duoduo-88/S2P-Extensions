# Build every tool and pack them into one release zip:
#
#   S2P-Extensions-v<Version>.zip
#   └─ S2P-Extensions\
#      ├─ README.md, README_zh-TW.md
#      └─ <Tool>\<Tool>.exe, <Tool>.s2p.json, README.md, README_zh-TW.md
#
# It also writes dist\s2p-extensions-updates.json, the update feed that S2P
# reads for Check for Updates.  Attach it to the GitHub release together with
# the zip: the tool manifests point at the latest release's copy.
#
# The user guides stay on GitHub (manual\ and <tool>\manual\); the READMEs in
# the zip link to them online.
#
#   powershell -ExecutionPolicy Bypass -File scripts\package_release.ps1
# Requires: Python 3.11+ with PyInstaller (pip install pyinstaller).
param(
    [string]$Python = "python",
    [string]$Version = ""
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

# Add a line here for each new tool: its folder under dist\ and its build script.
$tools = @(
    @{ Name = "S2P-Joystick-Macro"; Build = "macro\build.ps1" }
)

if (-not $Version) {
    $Version = (Get-Content -LiteralPath (Join-Path $repo "VERSION") -Raw).Trim()
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Bad version: $Version" }

& $Python -m unittest discover -s (Join-Path $repo "tests")
if ($LASTEXITCODE -ne 0) { throw "Tests failed; not packaging." }

$stage = Join-Path $repo "build\release"
$root = Join-Path $stage "S2P-Extensions"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $root | Out-Null
foreach ($name in @("README.md", "README_zh-TW.md")) {
    Copy-Item -LiteralPath (Join-Path $repo "release\$name") -Destination $root
}

foreach ($tool in $tools) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo $tool.Build) -Python $Python -SkipTests
    if ($LASTEXITCODE -ne 0) { throw "Build failed: $($tool.Name)" }
    $built = Join-Path $repo "dist\$($tool.Name)"
    $exe = Join-Path $built "$($tool.Name).exe"
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Missing $exe" }
    $target = Join-Path $root $tool.Name
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    foreach ($file in @("$($tool.Name).exe", "$($tool.Name).s2p.json", "README.md", "README_zh-TW.md")) {
        Copy-Item -LiteralPath (Join-Path $built $file) -Destination $target
    }
}

$feed = Join-Path $repo "dist\s2p-extensions-updates.json"
$manifests = @(foreach ($tool in $tools) { Join-Path $root "$($tool.Name)\$($tool.Name).s2p.json" })
& $Python (Join-Path $repo "scripts\tool_manifest.py") feed $Version $feed $manifests
if ($LASTEXITCODE -ne 0) { throw "Could not write the update feed." }

$zip = Join-Path $repo "dist\S2P-Extensions-v$Version.zip"
$hashPath = "$zip.sha256"
foreach ($old in @($zip, $hashPath)) {
    if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Force }
}
Compress-Archive -Path $root -DestinationPath $zip
# Same checksum file as S2P-XInput-Lite releases: "<HASH>  <zip name>".
$zipHash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
Set-Content -LiteralPath $hashPath -Value "$zipHash  $(Split-Path -Leaf $zip)" -Encoding ascii
Write-Host "Packed $zip"
Write-Host "SHA256 $zipHash"
Get-ChildItem -LiteralPath $root -Recurse -File |
    ForEach-Object { "  " + $_.FullName.Substring($stage.Length + 1) }
