# 1999RAG · 停止
# 用法: .\scripts\down.ps1 [-Purge]
param(
    [switch]$Purge      # 连数据卷一起删（⚠️ 会丢失索引，不可恢复）
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Purge) {
    Write-Host "[!] 将删除容器 + ./data/pgdata 与 ./data/rag_storage 索引数据" -ForegroundColor Red
    $ans = Read-Host "确认? 输入 yes 继续"
    if ($ans -ne "yes") { Write-Host "已取消"; exit 0 }
    docker compose down
    Remove-Item -Recurse -Force .\data\pgdata -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force .\data\rag_storage -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force .\data\inputs\__parsed__ -ErrorAction SilentlyContinue
    Write-Host "[ok] 已清理（语料与 state/ 清单保留）" -ForegroundColor Green
} else {
    docker compose down
    Write-Host "[ok] 已停止（数据保留）" -ForegroundColor Green
}
