[CmdletBinding()]
param(
    [switch]$SkipTests,
    [string]$OutputDirectory = "dist"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    $candidates = @(
        "C:\Users\ztli\AppData\Local\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python311\python.exe"
    ) | Where-Object { Test-Path -LiteralPath $_ }
    if (-not $candidates) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) { $candidates = @($pythonCommand.Source) }
    }
    if (-not $candidates) {
        throw "Python 3.11 or 3.12 was not found. Install a 64-bit Python, then rerun."
    }
    & $candidates[0] -m venv .venv
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed with exit code $LASTEXITCODE" }
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "dependency installation failed with exit code $LASTEXITCODE" }
if (-not $SkipTests) {
    & $venvPython -m pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }
}

# PyInstaller scans PATH while resolving native imports.  Keep unrelated
# developer tools out of that scan: a Poppler-provided ICU DLL can shadow the
# Windows ICU loaded by the PySide6 Qt runtime and make a frozen QtWidgets
# import fail.  This affects only the child build process, not the user PATH.
$previousPath = $env:PATH
$env:PATH = (($previousPath -split ';') | Where-Object {
    $_ -and $_ -notmatch '(?i)\\poppler\\'
}) -join ';'

$distRoot = Join-Path $projectRoot $OutputDirectory
try {
    & $venvPython -m PyInstaller --noconfirm --clean --distpath $distRoot SolarTimeDistanceExplorer.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
    $env:PATH = $previousPath
}
$exe = Join-Path $distRoot "SolarTimeDistanceExplorer\SolarTimeDistanceExplorer.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "PyInstaller completed without the expected executable: $exe"
}

# This waits for the bundled runtime to open and exit, exercising Qt plugins
# and imports without leaving the onedir DLLs locked for a subsequent build.
$env:STDE_SMOKE_TEST = "1"
$env:STDE_SMOKE_EXPORTS = "1"
$smoke = Start-Process -FilePath $exe -ArgumentList "--smoke-test" -Wait -PassThru -WindowStyle Hidden
$env:STDE_SMOKE_TEST = $null
$env:STDE_SMOKE_EXPORTS = $null
if ($smoke.ExitCode -ne 0) {
    throw "Bundled executable smoke test failed with exit code $($smoke.ExitCode)."
}

# Keep the distributable self-explanatory and package the complete onedir tree;
# the EXE cannot be separated from its bundled _internal runtime directory.
$appDirectory = Split-Path -Parent $exe
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $appDirectory -Force
$guideDirectory = Join-Path $appDirectory "docs"
New-Item -ItemType Directory -Path $guideDirectory -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "docs\UserGuide.md") -Destination $guideDirectory -Force
$version = (& $venvPython -c "from app.version import __version__; print(__version__)").Trim()
$releaseDirectory = Join-Path $projectRoot "release"
New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
$archive = Join-Path $releaseDirectory "SolarTimeDistanceExplorer-$version-Windows-x64.zip"
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
Compress-Archive -LiteralPath $appDirectory -DestinationPath $archive -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
$checksum = Join-Path $releaseDirectory "SolarTimeDistanceExplorer-$version-Windows-x64.sha256.txt"
Set-Content -LiteralPath $checksum -Value "$hash  $(Split-Path -Leaf $archive)" -Encoding ascii
Write-Host "Build and smoke test succeeded: $exe"
Write-Host "Release archive: $archive"
