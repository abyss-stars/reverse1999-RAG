# 1999RAG · 一键巡检
# 用法: .\scripts\status.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "=== 容器 ===" -ForegroundColor Cyan
docker compose ps

Write-Host "`n=== 健康检查 ===" -ForegroundColor Cyan
try {
    $h = Invoke-RestMethod -Uri "http://localhost:9621/health" -TimeoutSec 8
    Write-Host "  status        : $($h.status)"
    Write-Host "  core_version  : $($h.core_version)"
    Write-Host "  api_version   : $($h.api_version)"
    Write-Host "  workspace     : $($h.workspace)"
    Write-Host "  pipeline_busy : $($h.pipeline_busy)"
    Write-Host "  webui         : $($h.webui_available)   workspace入口: $($h.workspace_available)"
} catch {
    Write-Host "  [x] 无法连接 http://localhost:9621/health" -ForegroundColor Red
    Write-Host "      先跑: .\scripts\up.ps1" -ForegroundColor Yellow
}

Write-Host "`n=== 文档状态 ===" -ForegroundColor Cyan
try {
    $c = Invoke-RestMethod -Uri "http://localhost:9621/documents/status_counts" -TimeoutSec 8
    $c.status_counts.PSObject.Properties | ForEach-Object { "  $($_.Name) = $($_.Value)" }
} catch { Write-Host "  (取不到)" -ForegroundColor DarkGray }

Write-Host "`n=== 本地清单 ===" -ForegroundColor Cyan
if (Test-Path "state\index_manifest.json") {
    $m = Get-Content "state\index_manifest.json" -Raw | ConvertFrom-Json
    # 注意: PSMemberInfoIntegratingCollection 的 .Count 会做成员枚举,
    #       必须用 @() 包一层才是真实个数
    $docs = @($m.docs.PSObject.Properties)
    $done = @($docs | Where-Object { $_.Value.status -eq 'PROCESSED' }).Count
    $fail = @($docs | Where-Object { $_.Value.status -eq 'FAILED' }).Count
    Write-Host "  语料 commit : $($m.corpus.commit.Substring(0,8))"
    Write-Host "  章节总数    : $($docs.Count)"
    Write-Host "  已索引      : $done"
    if ($fail -gt 0) { Write-Host "  失败        : $fail" -ForegroundColor Red }
} else {
    Write-Host "  (manifest 未生成，先跑 pipeline\build_inputs.py)" -ForegroundColor DarkGray
}

# 注意: manifest 里的 staged 是"上次铺入时的标记"，处理完的文件会被
#       LightRAG 归档进 __parsed__/，所以要看实际目录而不是那个标记。
Write-Host "`n=== INPUT_DIR 实际状态 ===" -ForegroundColor Cyan
$top = @(Get-ChildItem "data\inputs" -File -Filter *.md -ErrorAction SilentlyContinue)
$arch = @(Get-ChildItem "data\inputs\__parsed__" -File -Filter *.md -ErrorAction SilentlyContinue)
Write-Host "  顶层待灌    : $($top.Count)"
Write-Host "  已归档      : $($arch.Count)   (data\inputs\__parsed\)"
