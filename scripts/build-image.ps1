# 1999RAG · 从本地 LightRAG 源码构建镜像
#
# 为什么需要这个脚本，而不是直接 docker compose build：
#   上游 Dockerfile 第一行是 `# syntax=docker/dockerfile:1`。
#   BuildKit 会因此去 Docker Hub 拉取 dockerfile frontend 镜像，而本机
#   BuildKit 不走 Docker Desktop 的代理配置，这一步必然超时失败：
#     failed to authorize: failed to fetch anonymous token ... auth.docker.io
#   解决：去掉该指令，改用 BuildKit 内建的 dockerfile frontend
#   （cache mount 等语法由内建 frontend 支持，功能不受影响）。
#
# 前提：基础镜像已本地化（拉取走守护进程代理，是通的）：
#   oven/bun:1
#   python:3.12-slim-bookworm
#   ghcr.io/astral-sh/uv:python3.12-bookworm-slim
#   ghcr.io/astral-sh/uv:latest
# 若缺失，脚本会自动预拉。
#
# 用法: .\scripts\build-image.ps1 [-Proxy http://host.docker.internal:7890]

param(
    [string]$Proxy = "http://host.docker.internal:7890",
    [switch]$NoCache
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$baseImages = @(
    "oven/bun:1",
    "python:3.12-slim-bookworm",
    "ghcr.io/astral-sh/uv:python3.12-bookworm-slim",
    "ghcr.io/astral-sh/uv:latest"
)

Write-Host "== 1/4 检查基础镜像 ==" -ForegroundColor Cyan
foreach ($img in $baseImages) {
    $found = docker images -q $img
    if (-not $found) {
        Write-Host "  -> 预拉 $img" -ForegroundColor Yellow
        docker pull $img
        if ($LASTEXITCODE -ne 0) { Write-Host "  [x] 拉取失败: $img" -ForegroundColor Red; exit 1 }
    } else {
        Write-Host "  [ok] $img"
    }
}

Write-Host "`n== 2/4 规范化 shell 脚本行尾 ==" -ForegroundColor Cyan
# 坑: 本机 git core.autocrlf=true, checkout 出来的 .sh 是 CRLF。
#     Linux 容器的 shebang 会变成 "#!/bin/sh\r" → 容器启动直接
#     "exec /usr/local/bin/docker-entrypoint.sh: no such file or directory"
#     并无限重启。转成 LF 即可。
#     (autocrlf=true 下 git 比较时会做 CRLF→LF 归一, 所以转 LF 后
#      LightRAG 工作区在 git status 里依然是干净的)
$shFixed = 0
Get-ChildItem "LightRAG" -Recurse -File -Filter *.sh -ErrorAction SilentlyContinue | ForEach-Object {
    $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
    if ($bytes -contains 13) {
        $text = [System.Text.Encoding]::UTF8.GetString($bytes) -replace "`r`n", "`n"
        [System.IO.File]::WriteAllText($_.FullName, $text, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "  -> LF: $($_.FullName.Replace("$root\", ''))"
        $shFixed++
    }
}
Write-Host "  [ok] 处理了 $shFixed 个文件"

Write-Host "`n== 3/4 生成去掉 syntax 指令的 Dockerfile ==" -ForegroundColor Cyan
if (-not (Test-Path "LightRAG\Dockerfile")) {
    Write-Host "  [x] 找不到 LightRAG\Dockerfile" -ForegroundColor Red; exit 1
}
New-Item -ItemType Directory -Force -Path "deploy" | Out-Null
Get-Content "LightRAG\Dockerfile" |
    Where-Object { $_ -notmatch '^#\s*syntax=' } |
    Set-Content "deploy\Dockerfile.lightrag" -Encoding UTF8
Write-Host "  -> deploy\Dockerfile.lightrag ($((Get-Content 'deploy\Dockerfile.lightrag').Count) 行)"

Write-Host "`n== 4/4 构建 lightrag-1999:local ==" -ForegroundColor Cyan
$args = @(
    "build",
    "-f", "deploy\Dockerfile.lightrag",
    "-t", "lightrag-1999:local",
    "--add-host", "host.docker.internal:host-gateway",
    "--build-arg", "HTTP_PROXY=$Proxy",
    "--build-arg", "HTTPS_PROXY=$Proxy",
    "--build-arg", "http_proxy=$Proxy",
    "--build-arg", "https_proxy=$Proxy",
    "--build-arg", "NO_PROXY=localhost,127.0.0.1,host.docker.internal"
)
if ($NoCache) { $args += "--no-cache" }
$args += "LightRAG"

docker @args
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n[x] 构建失败" -ForegroundColor Red
    Write-Host "    备用方案: 直接用官方镜像 v1.5.7（但没有 PGTableGraphStorage）" -ForegroundColor Yellow
    Write-Host "      docker pull ghcr.io/hkuds/lightrag:latest" -ForegroundColor Yellow
    exit 1
}

Write-Host "`n[ok] 构建完成" -ForegroundColor Green
docker images --format "  {{.Repository}}:{{.Tag}}  {{.Size}}" | Select-String lightrag
Write-Host "`n下一步: .\scripts\up.ps1"
