# Sunucuyu başlatır: http://localhost:8000 (sohbet) ve http://localhost:8000/admin
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
