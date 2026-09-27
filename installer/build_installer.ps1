# Task 28 installer build script (ASCII only)
# Builds release\DeltaHarmonicaHelper_Setup.exe from the verified onedir build.
# NOTE: keep ErrorActionPreference=Continue; PyInstaller writes INFO lines to stderr
# and PS 5.1 would otherwise treat them as terminating errors. We check explicit codes.
$ErrorActionPreference = "Continue"

$proj = "C:\Users\16966\Desktop\ds_w\delta-harmonica-helper"
$distApp = Join-Path $proj "dist\DeltaHarmonicaHelper"
$srcExe = Join-Path $distApp "DeltaHarmonicaHelper.exe"
$expected = "BCF4D68244723F1ACEAC2073D81D53ED1E89A5AEF0742B6FCCF15B3C7F706644"

Write-Host "=== 1. verify source EXE ==="
if (-not (Test-Path $srcExe)) { throw "source EXE not found: $srcExe" }
$h = (Get-FileHash $srcExe -Algorithm SHA256).Hash
Write-Host "source EXE SHA256 = $h"
if ($h -ne $expected) { throw "SOURCE EXE HASH MISMATCH (expected $expected)" }
Write-Host "source EXE hash: PASS"

$installerDir = Join-Path $proj "installer"
$build = Join-Path $installerDir "_build"
$release = Join-Path $proj "release"
$icon = Join-Path $installerDir "app.ico"

Write-Host ""
Write-Host "=== 2. clean previous build ==="
foreach ($d in @($build)) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
New-Item -ItemType Directory -Force -Path $build | Out-Null
New-Item -ItemType Directory -Force -Path $release | Out-Null

Write-Host ""
Write-Host "=== 3. extract app icon ==="
Add-Type -AssemblyName System.Drawing
$ico = [System.Drawing.Icon]::ExtractAssociatedIcon($srcExe)
$fs = [System.IO.File]::Create($icon)
$ico.Save($fs)
$fs.Close()
$ico.Dispose()
Write-Host ("icon -> {0} ({1} bytes)" -f $icon, (Get-Item $icon).Length)

Write-Host ""
Write-Host "=== 4. stage payload (app + uninstall.exe) ==="
$payload = Join-Path $build "payload"
$payloadApp = Join-Path $payload "app"
New-Item -ItemType Directory -Force -Path $payloadApp | Out-Null
Copy-Item -Path (Join-Path $distApp "*") -Destination $payloadApp -Recurse -Force
Write-Host ("payload/app files (raw): {0}" -f (Get-ChildItem $payloadApp -Recurse -File).Count)

# IMPORTANT: the frozen app keeps the user's score library inside its own directory
# (_internal\Scores).  That is USER DATA and must never ship inside a distributable
# installer, so strip any Scores folder out of the payload.
$userScores = Get-ChildItem $payloadApp -Recurse -Directory -Filter "Scores" -ErrorAction SilentlyContinue
foreach ($s in $userScores) {
    Write-Host ("  excluding user data from payload: {0} ({1} files)" -f $s.FullName, (Get-ChildItem $s.FullName -Recurse -File).Count)
    Remove-Item -Recurse -Force $s.FullName
}
Write-Host ("payload/app files (clean): {0}" -f (Get-ChildItem $payloadApp -Recurse -File).Count)
Copy-Item -Path (Join-Path $installerDir "uninstall_app.py") -Destination $payload -Force

Write-Host ""
Write-Host "=== 5. build uninstall.exe ==="
Push-Location $proj
& python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin `
  --icon $icon `
  --name uninstall `
  --distpath (Join-Path $build "un_dist") `
  --workpath (Join-Path $build "un_work") `
  --specpath $build `
  (Join-Path $installerDir "uninstall_app.py") 2>&1 | Select-Object -Last 3
$unExit = $LASTEXITCODE
Pop-Location
Write-Host "uninstaller build exit = $unExit"
if ($unExit -ne 0) { throw "uninstaller build failed" }
$unExe = Join-Path $build "un_dist\uninstall.exe"
if (-not (Test-Path $unExe)) { throw "uninstall.exe not produced" }
Copy-Item $unExe (Join-Path $payload "uninstall.exe") -Force
Remove-Item (Join-Path $payload "uninstall_app.py") -Force -ErrorAction SilentlyContinue
Write-Host ("uninstall.exe staged: {0} bytes" -f (Get-Item (Join-Path $payload "uninstall.exe")).Length)

Write-Host ""
Write-Host "=== 6. build setup (Setup.exe with embedded payload) ==="
Push-Location $proj
& python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin `
  --icon $icon `
  --name DeltaHarmonicaHelper_Setup `
  --add-data "$payload;payload" `
  --distpath (Join-Path $build "setup_dist") `
  --workpath (Join-Path $build "setup_work") `
  --specpath $build `
  (Join-Path $installerDir "setup_app.py") 2>&1 | Select-Object -Last 3
$setupExit = $LASTEXITCODE
Pop-Location
Write-Host "setup build exit = $setupExit"
if ($setupExit -ne 0) { throw "setup build failed" }

$setupExe = Join-Path $build "setup_dist\DeltaHarmonicaHelper_Setup.exe"
if (-not (Test-Path $setupExe)) { throw "Setup.exe not produced" }
$final = Join-Path $release "DeltaHarmonicaHelper_Setup.exe"
Copy-Item $setupExe $final -Force
Write-Host ""
Write-Host "=== 7. result ==="
Write-Host ("Setup.exe: {0}" -f $final)
Write-Host ("size     : {0} bytes" -f (Get-Item $final).Length)
Write-Host ("sha256   : {0}" -f (Get-FileHash $final -Algorithm SHA256).Hash)
