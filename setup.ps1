$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $venvPython)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        & py -3 -m venv .venv
    } else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($python -and $python.Source -notlike '*\WindowsApps\*') {
            & $python.Source -m venv .venv
        } else {
            $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
            if (-not (Test-Path -LiteralPath $bundledPython)) {
                throw 'Install Python 3.11 or newer for Windows first.'
            }
            & $bundledPython -m venv .venv
        }
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python virtual environment.' }
    if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Python virtual environment was not created.' }
}

& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install Python dependencies.' }
& $venvPython -m camoufox fetch
if ($LASTEXITCODE -ne 0) { throw 'Could not fetch Camoufox or GeoIP data.' }
& $venvPython -c "from launcher.browser import installed_browser; print(installed_browser()[0])"
if ($LASTEXITCODE -ne 0) { throw 'Camoufox executable is missing after fetch.' }
Write-Host 'Setup complete. Double-click start.cmd to launch.'
