# 本脚本把后端镜像构建所需的 apt 系统依赖下载为离线 deb 包，输出到 backend/offline/apt。
# 依赖 Docker：容器基础镜像与 backend/Dockerfile 保持一致，确保下载到的 deb 包可直接在该镜像内安装。
[CmdletBinding()]
param(
    [ValidateSet("amd64", "arm64")]
    [string]$Architecture = "amd64",

    [string]$DebianRelease = "bookworm",

    [string]$BaseImage = "docker.m.daocloud.io/library/python:3.10-slim-bookworm",

    [string]$AptMirror = "http://mirrors.tuna.tsinghua.edu.cn/debian",

    # 与 backend/Dockerfile 的 ARG APT_PACKAGES 保持一致，改动时必须两处同步。
    [string[]]$Packages = @(
        "git",
        "ca-certificates",
        "curl",
        "libgomp1",
        "libgl1",
        "libglib2.0-0",
        "unzip",
        "libarchive-tools",
        "p7zip-full",
        "7zip"
    ),

    [switch]$SkipVerify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputDir = Join-Path $projectRoot "backend/offline/apt"
$scriptsDir = Join-Path $projectRoot "scripts"

foreach ($scriptName in @("apt-offline-download.sh", "apt-offline-verify.sh")) {
    $scriptPath = Join-Path $scriptsDir $scriptName
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "缺少离线脚本：$scriptPath"
    }
    # 容器内直接执行脚本文件，CRLF 会让 sh 解析失败，这里提前拦截。
    if ([IO.File]::ReadAllBytes($scriptPath) -contains 13) {
        throw "脚本包含 CRLF 行尾，请先转为 LF：$scriptPath"
    }
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

function Invoke-DockerCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host "docker $($Arguments -join ' ')"
    & docker @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker 命令执行失败，退出码：$LASTEXITCODE"
    }
}

Invoke-DockerCommand -Arguments (@(
    "run", "--rm",
    "--platform", "linux/$Architecture",
    "--volume", "$($scriptsDir):/scripts:ro",
    "--volume", "$($outputDir):/out",
    $BaseImage,
    "sh", "/scripts/apt-offline-download.sh",
    $DebianRelease, $AptMirror
) + $Packages)

$targetDir = Join-Path $outputDir "$DebianRelease-$Architecture"
$debFiles = @(Get-ChildItem -LiteralPath $targetDir -Filter "*.deb" -File -ErrorAction SilentlyContinue)
if ($debFiles.Count -eq 0) {
    throw "没有生成任何 deb 包：$targetDir"
}
$totalSize = [Math]::Round((($debFiles | Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host "离线 deb 包目录：$targetDir"
Write-Host "包数量：$($debFiles.Count)，总大小：$totalSize MB"

if (-not $SkipVerify) {
    # 断网安装自检：只有 deb 包齐全且能离线安装，才能说明该离线依赖包可用。
    Invoke-DockerCommand -Arguments @(
        "run", "--rm",
        "--platform", "linux/$Architecture",
        "--network", "none",
        "--volume", "$($scriptsDir):/scripts:ro",
        "--volume", "$($outputDir):/opt/apt-offline:ro",
        $BaseImage,
        "sh", "/scripts/apt-offline-verify.sh",
        $DebianRelease, $Architecture
    )
}

Write-Host "离线 apt 依赖已就绪：backend/offline/apt/$DebianRelease-$Architecture"
