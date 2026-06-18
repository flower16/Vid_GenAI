<#
.SYNOPSIS
    Launch the Streamlit app using the project's virtual environment.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\run_app.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    throw "Virtual environment not found. Run scripts\setup.ps1 first."
}

& $venvPy -m streamlit run src\app.py
