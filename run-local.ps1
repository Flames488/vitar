$ErrorActionPreference = "Stop"

$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"

if (-not (Test-Path -LiteralPath $docker)) {
    throw "Docker Desktop CLI not found at $docker"
}

Set-Location -LiteralPath $PSScriptRoot
& $docker compose up --build --detach
& $docker compose ps

Write-Host ""
Write-Host "Vitar is running:"
Write-Host "  API:      http://localhost:8000/health"
Write-Host "  Frontend: http://localhost:3002"
Write-Host "  Nginx:    http://localhost"
