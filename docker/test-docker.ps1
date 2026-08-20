# Docker 配置测试脚本 (PowerShell)
# 用法: .\docker\test-docker.ps1

$ErrorActionPreference = "Stop"

function Log-Info { Write-Host "[INFO] $args" -ForegroundColor Green }
function Log-Warn { Write-Host "[WARN] $args" -ForegroundColor Yellow }
function Log-Error { Write-Host "[ERROR] $args" -ForegroundColor Red }

# ── 测试 Docker 配置 ──────────────────────────────────────────────────────────
function Test-DockerConfig {
    Log-Info "测试 Docker 配置..."

    $requiredFiles = @(
        "Dockerfile",
        "docker\compose.yml",
        "docker\entrypoint.sh",
        "docker\.env.example"
    )

    foreach ($file in $requiredFiles) {
        if (Test-Path $file) {
            Log-Info "  $file 存在"
        } else {
            Log-Error "  $file 不存在"
            exit 1
        }
    }

    # 检查 compose 文件语法
    Log-Info "检查 compose 文件语法..."
    $result = docker compose -f docker\compose.yml config --quiet 2>&1
    if ($LASTEXITCODE -eq 0) {
        Log-Info "  compose.yml 语法正确"
    } else {
        Log-Error "  compose.yml 语法错误"
        exit 1
    }

    Log-Info "Docker 配置测试完成"
}

# ── 测试环境配置 ──────────────────────────────────────────────────────────────
function Test-EnvConfig {
    Log-Info "测试环境配置..."

    if (Test-Path "docker\.env") {
        Log-Info "  docker\.env 存在"

        $content = Get-Content "docker\.env" -Raw
        $requiredVars = @("DB_PG_DEFAULT_USER", "DB_PG_DEFAULT_PASSWORD", "DB_PG_DEFAULT_DB")

        foreach ($var in $requiredVars) {
            if ($content -match "^${var}=") {
                Log-Info "  $var 已配置"
            } else {
                Log-Warn "  $var 未配置"
            }
        }
    } else {
        Log-Warn "  docker\.env 不存在（将从示例创建）"
    }
}

# ── 测试 Docker 构建 ──────────────────────────────────────────────────────────
function Test-DockerBuild {
    Log-Info "测试 Docker 构建..."

    docker build -t service-mcp-test . 2>&1 | Select-Object -Last 5
    if ($LASTEXITCODE -eq 0) {
        Log-Info "  Docker 镜像构建成功"
        docker rmi service-mcp-test 2>$null
    } else {
        Log-Error "  Docker 镜像构建失败"
        exit 1
    }
}

# ── 主函数 ────────────────────────────────────────────────────────────────────
function Main {
    Log-Info "开始 Docker 配置测试..."
    Write-Host ""

    # 切换到项目根目录
    Set-Location (Split-Path $PSScriptRoot -Parent)

    Test-DockerConfig
    Write-Host ""

    Test-EnvConfig
    Write-Host ""

    $reply = Read-Host "是否测试 Docker 构建？(y/N)"
    if ($reply -match "^[Yy]$") {
        Test-DockerBuild
    } else {
        Log-Info "跳过 Docker 构建测试"
    }

    Write-Host ""
    Log-Info "测试完成！"
    Log-Info "使用以下命令启动服务："
    Log-Info "  .\docker\ctl.ps1 -Action deploy -Env prod"
}

Main
