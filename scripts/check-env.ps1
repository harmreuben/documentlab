# DocumentLab - Phase 2 environment check
# Run from the project root:  .\scripts\check-env.ps1

function Check-Tool($name, $command) {
    try {
        $out = & $command 2>&1 | Select-Object -First 1
        Write-Host ("[OK]      {0,-10} {1}" -f $name, $out) -ForegroundColor Green
    } catch {
        Write-Host ("[MISSING] {0,-10} not found on PATH" -f $name) -ForegroundColor Red
    }
}

Write-Host "`n== Tools ==" -ForegroundColor Cyan
Check-Tool "Python"    { python --version }
Check-Tool "pip"       { python -m pip --version }
Check-Tool "Git"       { git --version }
Check-Tool "Node"      { node --version }
Check-Tool "npm"       { npm --version }
Check-Tool "Tesseract" { tesseract --version }

Write-Host "`n== Virtual environment ==" -ForegroundColor Cyan
if ($env:VIRTUAL_ENV) {
    Write-Host "[OK]      Active: $env:VIRTUAL_ENV" -ForegroundColor Green
} else {
    Write-Host "[WARN]    No virtual environment active" -ForegroundColor Yellow
}

Write-Host "`n== Python libraries ==" -ForegroundColor Cyan
python "$PSScriptRoot\check_libs.py"
