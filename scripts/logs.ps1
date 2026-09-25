# 1999RAG · 看日志
# 用法: .\scripts\logs.ps1 [-Service lightrag|postgres] [-Tail 100] [-Follow]

param(
    [string]$Service = "lightrag",
    [int]$Tail = 100,
    [switch]$Follow
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Follow) {
    docker compose logs -f --tail $Tail $Service
} else {
    docker compose logs --tail $Tail $Service
}
