# DocumentLab - start in production mode (Waitress + the built website on one port)
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File C:\Projects\documentlab\scripts\start-production.ps1
# Settings come from backend\.env (see docs\DEPLOYMENT.md). Stop with Ctrl+C.

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "..\backend" | Resolve-Path
$python  = Join-Path $backend ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "The virtual environment is missing: $python" }

$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
Set-Location $backend

& $python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw "Database update failed; DocumentLab was not started." }
& $python manage.py collectstatic --noinput -v 0
if ($LASTEXITCODE -ne 0) { throw "Collecting static files failed; DocumentLab was not started." }

# Add  --host 0.0.0.0  only when an HTTPS proxy is in front (docs\DEPLOYMENT.md, step 7).
& $python manage.py serve --port 8000
