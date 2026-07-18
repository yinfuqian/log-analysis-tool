param(
    [switch]$DryRun,
    [switch]$KeepReleaseArtifacts,
    [string]$WorkspaceRoot = (Split-Path -Parent $PSScriptRoot)
)

# 本脚本只清理明确允许的缓存、依赖和构建产物，并在每次删除前校验工作区边界。
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:ResolvedWorkspace = (Resolve-Path -LiteralPath $WorkspaceRoot).Path.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
$script:RemovedCount = 0
$script:ProtectedLeafNames = @(".env", "users.csv")

function Test-PathInsideWorkspace {
    param([Parameter(Mandatory = $true)][string]$Path)

    # 统一转换为绝对路径，并要求目标等于工作区或位于工作区目录分隔符之后。
    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $prefix = $script:ResolvedWorkspace + [IO.Path]::DirectorySeparatorChar
    return $fullPath.Equals($script:ResolvedWorkspace, [StringComparison]::OrdinalIgnoreCase) -or
        $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Remove-ApprovedAbsolutePath {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    $resolved = (Resolve-Path -LiteralPath $Path).Path
    if (-not (Test-PathInsideWorkspace -Path $resolved)) {
        throw "拒绝删除工作区之外的路径：$resolved"
    }
    if ($resolved.Equals($script:ResolvedWorkspace, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝删除工作区根目录"
    }

    $leafName = Split-Path -Leaf $resolved
    if ($script:ProtectedLeafNames -contains $leafName) {
        throw "拒绝删除受保护文件：$resolved"
    }

    if ($DryRun) {
        Write-Output "[预览] $resolved"
        return
    }

    Remove-Item -LiteralPath $resolved -Recurse -Force
    $script:RemovedCount += 1
    Write-Output "[已删除] $resolved"
}

function Remove-ApprovedRelativePath {
    param([Parameter(Mandatory = $true)][string]$RelativePath)

    # 所有固定目标都从已解析的工作区根目录拼接，禁止调用方传入工作区外路径。
    $candidate = [IO.Path]::GetFullPath((Join-Path $script:ResolvedWorkspace $RelativePath))
    if (-not (Test-PathInsideWorkspace -Path $candidate)) {
        throw "拒绝处理工作区之外的相对路径：$RelativePath"
    }
    Remove-ApprovedAbsolutePath -Path $candidate
}

function Get-PythonCacheDirectories {
    # 使用队列自顶向下遍历，在进入虚拟环境、依赖和构建目录前剪枝，避免访问链接目录。
    $targets = New-Object System.Collections.Generic.List[string]
    $queue = New-Object System.Collections.Generic.Queue[string]
    $queue.Enqueue($script:ResolvedWorkspace)
    $skipDirectories = @(".git", ".venv", ".venv-win", "node_modules", "dist", "build")

    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        $children = Get-ChildItem -LiteralPath $current -Directory -Force -ErrorAction SilentlyContinue
        foreach ($child in $children) {
            if ($child.Name -eq "__pycache__") {
                $targets.Add($child.FullName)
                continue
            }
            if ($skipDirectories -contains $child.Name) {
                continue
            }
            if (Test-PathInsideWorkspace -Path $child.FullName) {
                $queue.Enqueue($child.FullName)
            }
        }
    }
    return $targets
}

# 固定允许列表不包含配置、用户 CSV、源码、测试、文档或前端 Webpack build 辅助源码。
$generatedTargets = @(
    ".pytest_cache",
    ".mypy_cache",
    "backend\.pytest_cache",
    "backend\.mypy_cache",
    "backend\app\logs",
    "frontend\app\log-analyze\node_modules",
    "frontend\app\log-analyze\dist",
    "frontend\app\log-analyze\coverage",
    "windows-client\build",
    "frontend\tmp.vue",
    "project-info-output.tar.gz",
    "windows-client\FaultAnalyzerClient.spec"
)

foreach ($relativePath in $generatedTargets) {
    Remove-ApprovedRelativePath -RelativePath $relativePath
}

foreach ($cacheDirectory in Get-PythonCacheDirectories) {
    Remove-ApprovedAbsolutePath -Path $cacheDirectory
}

if (-not $KeepReleaseArtifacts) {
    Remove-ApprovedRelativePath -RelativePath "windows-client\dist"
}

if ($DryRun) {
    Write-Output "清理预览完成；未删除任何文件。"
} else {
    Write-Output "安全清理完成，共删除 $script:RemovedCount 个目标。"
}
