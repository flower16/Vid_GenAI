<#
.SYNOPSIS
    Run the four experiments (A-D) and generate the comparison report.
.PARAMETER NoRagas
    Skip the slower RAGAS answer-quality stage.
.PARAMETER SkipBuild
    Reuse existing FAISS indexes instead of rebuilding them.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\run_experiments.ps1 -NoRagas
#>
[CmdletBinding()]
param(
    [switch]$NoRagas,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    throw "Virtual environment not found. Run scripts\setup.ps1 first."
}

$cmdArgs = @("run_experiments.py")
if ($NoRagas)   { $cmdArgs += "--no-ragas" }
if ($SkipBuild) { $cmdArgs += "--skip-build" }

& $venvPy @cmdArgs
