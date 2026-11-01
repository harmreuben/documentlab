# DocumentLab - daily maintenance: delete expired identity data, then back up.
# Schedule it once a day with Windows Task Scheduler (docs\DEPLOYMENT.md, step 9):
#   Program:   powershell.exe
#   Arguments: -ExecutionPolicy Bypass -File C:\Projects\documentlab\scripts\daily-maintenance.ps1
# Output is appended to backend\logs\maintenance.log.

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "..\backend" | Resolve-Path
$python  = Join-Path $backend ".venv\Scripts\python.exe"
$log     = Join-Path $backend "logs\maintenance.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
Set-Location $backend

function Run($label, [string[]]$arguments) {
    Add-Content $log ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $label)
    & $python manage.py @arguments 2>&1 | Add-Content $log
    if ($LASTEXITCODE -ne 0) { Add-Content $log "  FAILED (exit code $LASTEXITCODE)"; exit $LASTEXITCODE }
}

Run "Deleting expired identity data" @("purge_documents")
Run "Backing up the database and uploaded files" @("backup_data", "--include-files")
Add-Content $log "  Done."
