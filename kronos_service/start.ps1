param(
    [int]$Port = 8101,
    [switch]$Cpu
)

$ErrorActionPreference = "Stop"
$ServiceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ServiceRoot
$PythonExe = Join-Path $ServiceRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = (Get-Command python -ErrorAction Stop).Source
}

$env:KRONOS_SERVICE_ROOT = $ServiceRoot
$env:KRONOS_SOURCE_DIR = $ServiceRoot
$env:KRONOS_MODEL_ROOT = $ServiceRoot
$env:KRONOS_SERVICE_PORT = $Port
if ($Cpu) { $env:CUDA_VISIBLE_DEVICES = "" }

Set-Location $ServiceRoot
Write-Host "Starting WissenQuant Kronos microservice..." -ForegroundColor Cyan
Write-Host "Root: $ServiceRoot" -ForegroundColor Gray
Write-Host "URL:  http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "CPU mode: $Cpu" -ForegroundColor Gray

& $PythonExe "main.py"
