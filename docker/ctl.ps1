# 使用方法: .\docker\ctl.ps1 <命令> [选项]

param(
    [Parameter(Position=0)]
    [string]$Command = "",

    [string]$e = "prod",
    [string]$env = "",
    [string]$p = "",
    [string]$profile = "",
    [string]$s = "",
    [string]$service = "",
    [switch]$b = $false,
    [switch]$build = $false,
    [switch]$v = $false,
    [switch]$volumes = $false,
    [switch]$h = $false,
    [switch]$help = $false
)

# 设置错误处理
$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Step {
    param([string]$Message)
    Write-Host "[STEP] $Message" -ForegroundColor Blue
}

function Show-Help {
    Write-Host "Service MCP 管理脚本" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "用法: .\docker\ctl.ps1 <命令> [选项]" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "命令:" -ForegroundColor Yellow
    Write-Host "  deploy    部署服务（首次部署）"
    Write-Host "  start     启动服务（已停止的服务）"
    Write-Host "  stop      停止服务"
    Write-Host "  update    更新服务（重新构建）"
    Write-Host "  logs      查看日志"
    Write-Host "  test      测试配置"
    Write-Host "  help      显示此帮助信息"
    Write-Host ""
    Write-Host "选项:" -ForegroundColor Yellow
    Write-Host "  -e, --env ENV        环境类型: prod(生产), dev(开发), test(测试) [默认: prod]"
    Write-Host "  -p, --profile PROF   启用的 profile: admin(pgAdmin) [默认: 无]"
    Write-Host "  -s, --service SVC    查看特定服务的日志（仅 logs 命令）"
    Write-Host "  -b, --build          强制重新构建镜像（仅 deploy/update 命令）"
    Write-Host "  -v, --volumes        同时删除数据卷（仅 stop 命令）"
    Write-Host ""
    Write-Host "示例:" -ForegroundColor Yellow
    Write-Host "  .\docker\ctl.ps1 deploy              # 部署生产环境"
    Write-Host "  .\docker\ctl.ps1 deploy -e dev       # 部署开发环境"
    Write-Host "  .\docker\ctl.ps1 start               # 启动服务"
    Write-Host "  .\docker\ctl.ps1 stop                # 停止服务"
    Write-Host "  .\docker\ctl.ps1 update -b           # 强制重新构建并更新"
    Write-Host "  .\docker\ctl.ps1 logs                # 查看所有日志"
    Write-Host "  .\docker\ctl.ps1 logs -s app         # 查看应用日志"
    Write-Host "  .\docker\ctl.ps1 test                # 测试配置"
}

function Test-DockerEnvironment {
    # 检查 Docker 是否安装
    try {
        docker --version 2>&1 | Out-Null
    }
    catch {
        Write-Error "Docker 未安装，请先安装 Docker Desktop"
        exit 1
    }

    # 检查 Docker 是否运行
    try {
        docker info 2>&1 | Out-Null
    }
    catch {
        Write-Error "Docker 服务未启动，请启动 Docker Desktop"
        exit 1
    }
}

function Get-ComposeFiles {
    param([string]$Environment)

    switch ($Environment) {
        "prod" { return "-f docker\compose.yml" }
        "production" { return "-f docker\compose.yml" }
        "dev" { return "-f docker\compose.yml -f docker\compose.dev.yml --env-file docker\.env.dev" }
        "development" { return "-f docker\compose.yml -f docker\compose.dev.yml --env-file docker\.env.dev" }
        "test" { return "-f docker\compose.yml -f docker\compose.test.yml --env-file docker\.env.test" }
        default {
            Write-Error "未知环境: $Environment (支持: prod, dev, test)"
            exit 1
        }
    }
}

function New-EnvFile {
    param([string]$Environment)

    $envFile = "docker\.env"

    # 只有生产环境需要检查 .env 文件
    if ($Environment -eq "prod" -or $Environment -eq "production") {
        if (-not (Test-Path $envFile)) {
            Write-Warn "环境配置文件不存在，将从示例创建..."
            $exampleFile = "docker\.env.example"

            if (Test-Path $exampleFile) {
                Copy-Item $exampleFile $envFile
                Write-Info "已创建环境配置文件: $envFile (基于 $exampleFile)"
                Write-Warn "请编辑 $envFile 修改配置后重新运行"
                exit 0
            }
            else {
                Write-Error "找不到环境配置示例文件: $exampleFile"
                exit 1
            }
        }
    }
}

function Invoke-Deploy {
    Write-Step "部署 Service MCP 服务 (环境: $e)..."

    # 检查 Docker 环境
    Test-DockerEnvironment

    # 创建环境配置文件
    New-EnvFile -Environment $e

    # 获取 compose 文件
    $composeFiles = Get-ComposeFiles -Environment $e

    # 添加 profile
    $profileFlag = ""
    if ($p -ne "") {
        $profileFlag = "--profile $p"
    }

    # 构建标志
    $buildFlag = ""
    if ($b) {
        Write-Warn "将重新构建镜像..."
        $buildFlag = "--build"
    }

    # 执行部署
    Invoke-Expression "docker compose $composeFiles $profileFlag up -d $buildFlag"

    Write-Info "部署完成！"
    Write-Info "使用 '.\docker\ctl.ps1 logs' 查看日志"
    Write-Info "使用 '.\docker\ctl.ps1 stop' 停止服务"
}

function Invoke-Start {
    Write-Step "启动 Service MCP 服务 (环境: $e)..."

    # 检查 Docker 环境
    Test-DockerEnvironment

    # 获取 compose 文件
    $composeFiles = Get-ComposeFiles -Environment $e

    # 添加 profile
    $profileFlag = ""
    if ($p -ne "") {
        $profileFlag = "--profile $p"
    }

    # 执行启动
    Invoke-Expression "docker compose $composeFiles $profileFlag up -d"

    Write-Info "服务已启动"
    Write-Info "使用 '.\docker\ctl.ps1 logs' 查看日志"
    Write-Info "使用 '.\docker\ctl.ps1 stop' 停止服务"
}

function Invoke-Stop {
    Write-Step "停止 Service MCP 服务 (环境: $e)..."

    # 检查 Docker 环境
    Test-DockerEnvironment

    # 获取 compose 文件
    $composeFiles = Get-ComposeFiles -Environment $e

    # 执行停止
    if ($v) {
        Write-Warn "警告: 将同时删除数据卷！"
        $confirm = Read-Host "确认删除数据卷？(y/N)"
        if ($confirm -eq "y" -or $confirm -eq "Y") {
            Invoke-Expression "docker compose $composeFiles down -v"
            Write-Info "服务已停止，数据卷已删除"
        }
        else {
            Write-Info "取消操作"
            exit 0
        }
    }
    else {
        Invoke-Expression "docker compose $composeFiles down"
        Write-Info "服务已停止"
    }
}

function Invoke-Update {
    Write-Step "更新 Service MCP 服务 (环境: $e)..."

    # 检查 Docker 环境
    Test-DockerEnvironment

    # 获取 compose 文件
    $composeFiles = Get-ComposeFiles -Environment $e

    # 构建标志
    $buildFlag = ""
    if ($b) {
        Write-Warn "将重新构建镜像..."
        $buildFlag = "--build"
    }

    # 执行更新
    Invoke-Expression "docker compose $composeFiles up -d $buildFlag"

    Write-Info "服务已更新"
    Write-Info "使用 '.\docker\ctl.ps1 logs' 查看日志"
}

function Invoke-Logs {
    Write-Step "查看日志 (环境: $e)..."

    # 检查 Docker 环境
    Test-DockerEnvironment

    # 获取 compose 文件
    $composeFiles = Get-ComposeFiles -Environment $e

    # 执行日志查看
    if ($s -ne "") {
        Invoke-Expression "docker compose $composeFiles logs -f $s"
    }
    else {
        Invoke-Expression "docker compose $composeFiles logs -f"
    }
}

function Invoke-Test {
    Write-Step "测试配置..."

    # 检查 Docker 环境
    Test-DockerEnvironment

    # 测试 compose 配置
    Write-Info "测试 compose 配置..."
    try {
        docker compose -f docker\compose.production.yml config --quiet 2>&1 | Out-Null
        Write-Info "✓ compose.production.yml 配置正确"
    }
    catch {
        Write-Error "✗ compose.production.yml 配置错误"
        exit 1
    }

    # 测试环境配置
    Write-Info "测试环境配置..."
    if (Test-Path "docker\.env") {
        Write-Info "✓ docker\.env 存在"
    }
    else {
        Write-Warn "⚠ docker\.env 不存在"
    }

    Write-Info "测试完成！"
}

function Main {
    # 处理参数
    if ($env -ne "") { $e = $env }
    if ($profile -ne "") { $p = $profile }
    if ($service -ne "") { $s = $service }
    if ($build) { $b = $true }
    if ($volumes) { $v = $true }
    if ($help) { $h = $true }

    # 切换到项目根目录
    $projectRoot = Split-Path -Parent $PSScriptRoot
    Set-Location $projectRoot

    # 执行命令
    switch ($Command) {
        "deploy" { Invoke-Deploy }
        "start" { Invoke-Start }
        "stop" { Invoke-Stop }
        "update" { Invoke-Update }
        "logs" { Invoke-Logs }
        "test" { Invoke-Test }
        "help" { Show-Help }
        "" { Show-Help }
        default {
            Write-Error "未知命令: $Command"
            Show-Help
            exit 1
        }
    }
}

Main
