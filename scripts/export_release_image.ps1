# 本脚本一次导出一个指定镜像，并生成可在生产服务器核验的 SHA256 摘要文件。
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Image,

    [string]$OutputDirectory = "release/images",

    [string]$OutputFileName = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$outputPath = if ([IO.Path]::IsPathRooted($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
}
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

& docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    throw "本机不存在镜像：$Image"
}

if (-not $OutputFileName) {
    $safeName = $Image -replace '[^A-Za-z0-9._-]', '-'
    $OutputFileName = "$safeName.tar"
}
if (-not $OutputFileName.EndsWith(".tar", [StringComparison]::OrdinalIgnoreCase)) {
    $OutputFileName = "$OutputFileName.tar"
}

$tarPath = Join-Path $outputPath $OutputFileName
Write-Host "docker save --output $tarPath $Image"
& docker save --output $tarPath $Image
if ($LASTEXITCODE -ne 0) {
    throw "镜像导出失败，退出码：$LASTEXITCODE"
}

$hash = (Get-FileHash -Algorithm SHA256 -Path $tarPath).Hash.ToLowerInvariant()
$hashPath = "$tarPath.sha256"
Set-Content -Path $hashPath -Encoding ascii -NoNewline -Value "$hash  $([IO.Path]::GetFileName($tarPath))`n"

Write-Host "镜像导出完成：$tarPath"
Write-Host "SHA256：$hash"
Write-Host "摘要文件：$hashPath"
