# 1999RAG · 启动整套栈
# 用法: .\scripts\up.ps1  [-Build]
param(
    [switch]$Build,                      # 是否重建 lightrag 镜像
    [int]$TimeoutSec = 180               # 等待 lightrag 就绪的上限
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1999RAG 启动 ==" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "[!] 缺少 .env。请先: Copy-Item .env.example .env 并填入 API Key" -ForegroundColor Red
    exit 1
}

# 检查 .env 里的占位符是否还没改
$envText = Get-Content ".env" -Raw
if ($envText -match 'sk-REPLACE_ME') {
    Write-Host "[!] .env 里仍有 sk-REPLACE_ME 占位符，请先填入真实 API Key" -ForegroundColor Yellow
    Write-Host "    需要填的变量:" -ForegroundColor Yellow
    Write-Host "      LLM_BINDING_API_KEY" -ForegroundColor Yellow
    Write-Host "      EMBEDDING_BINDING_API_KEY" -ForegroundColor Yellow
    exit 1
}

if ($Build) {
    Write-Host "-> 构建镜像 ..." -ForegroundColor Yellow
    & "$PSScriptRoot\build-image.ps1"
    if ($LASTEXITCODE -ne 0) { Write-Host "[x] 构建失败" -ForegroundColor Red; exit 1 }
} else {
    $img = docker images -q lightrag-1999:local
    if (-not $img) {
        Write-Host "-> 镜像 lightrag-1999:local 不存在，先构建 ..." -ForegroundColor Yellow
        & "$PSScriptRoot\build-image.ps1"
        if ($LASTEXITCODE -ne 0) { Write-Host "[x] 构建失败" -ForegroundColor Red; exit 1 }
    }
}

Write-Host "-> 启动容器 ..." -ForegroundColor Yellow
docker compose up -d
if ($LASTEXITCODE -ne 0) { Write-Host "[x] 启动失败" -ForegroundColor Red; exit 1 }

Write-Host "-> 等待 lightrag 就绪 (最多 ${TimeoutSec}s) ..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt [int]($TimeoutSec / 3); $i++) {
    Start-Sleep -Seconds 3
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:9621/health" -TimeoutSec 5
        if ($r.status -eq "ok" -or $r.status) {
            Write-Host "   [ok] 就绪 ($(($i+1)*3)s)  core=$($r.core_version)" -ForegroundColor Green
            $ready = $true
            break
        }
    } catch { }
    Write-Host "   [$((($i+1)*3))s] 等待中..." -ForegroundColor DarkGray
}

if (-not $ready) {
    Write-Host "[!] 超时。查看日志: docker compose logs --tail 50 lightrag" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "== 就绪 ==" -ForegroundColor Green
Write-Host "  WebUI    : http://localhost:9621/webui"
Write-Host "  问答入口 : http://localhost:9621/workspace"
Write-Host "  API 文档 : http://localhost:9621/docs"
Write-Host "  健康检查 : http://localhost:9621/health"
Write-Host ""
Write-Host "下一步: python pipeline/ingest.py --scan   # 灌入 81 章"
