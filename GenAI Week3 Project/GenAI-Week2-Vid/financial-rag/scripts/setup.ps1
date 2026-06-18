<#
.SYNOPSIS
    One-shot environment setup for the Financial RAG project on Windows.
.DESCRIPTION
    Creates a virtual environment, installs dependencies, and scaffolds the .env
    file. Run from anywhere — the script locates the project root itself.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#>
[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

# Resolve project root (parent of this scripts\ folder).
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "Project root: $Root" -ForegroundColor Cyan

# 1. Check Python version (need 3.11+).
$verRaw = & $Python --version
Write-Host "Found $verRaw"
$ver = [version](($verRaw -replace 'Python\s+', '') -split '\+')[0]
if ($ver -lt [version]"3.11") {
    throw "Python 3.11+ required, found $ver. Install from https://www.python.org/downloads/"
}

# 2. Create the virtual environment.
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment (.venv)..." -ForegroundColor Cyan
    & $Python -m venv .venv
} else {
    Write-Host ".venv already exists - reusing it." -ForegroundColor Yellow
}

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

# 3. Install dependencies.
Write-Host "Upgrading pip and installing requirements (this can take a few minutes)..." -ForegroundColor Cyan
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt

# 4. Scaffold .env.
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from template - EDIT IT and set OPENAI_API_KEY." -ForegroundColor Yellow
} else {
    Write-Host ".env already exists - leaving it untouched." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "  1. Edit .env and set OPENAI_API_KEY=sk-..."
Write-Host "  2. .\.venv\Scripts\Activate.ps1     # activate the environment"
Write-Host "  3. python run_experiments.py         # or: streamlit run src\app.py"
