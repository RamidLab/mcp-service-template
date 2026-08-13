#!/bin/bash
set -e

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# 显示帮助
show_help() {
    echo -e "${CYAN}Service MCP 管理脚本${NC}"
    echo ""
    echo -e "${YELLOW}用法:${NC} $0 <命令> [选项]"
    echo ""
    echo -e "${YELLOW}命令:${NC}"
    echo "  deploy    部署服务（首次部署）"
    echo "  start     启动服务（已停止的服务）"
    echo "  stop      停止服务"
    echo "  update    更新服务（重新构建）"
    echo "  logs      查看日志"
    echo "  test      测试配置"
    echo "  help      显示此帮助信息"
    echo ""
    echo -e "${YELLOW}选项:${NC}"
    echo "  -e, --env ENV        环境类型: prod(生产), dev(开发), test(测试) [默认: prod]"
    echo "  -p, --profile PROF   启用的 profile: admin(pgAdmin) [默认: 无]"
    echo "  -s, --service SVC    查看特定服务的日志（仅 logs 命令）"
    echo "  -b, --build          强制重新构建镜像（仅 deploy/update 命令）"
    echo "  -v, --volumes        同时删除数据卷（仅 stop 命令）"
    echo "  -h, --help           显示帮助信息"
    echo ""
    echo -e "${YELLOW}示例:${NC}"
    echo "  $0 deploy              # 部署生产环境"
    echo "  $0 deploy -e dev       # 部署开发环境"
    echo "  $0 start               # 启动服务"
    echo "  $0 stop                # 停止服务"
    echo "  $0 update -b           # 强制重新构建并更新"
    echo "  $0 logs                # 查看所有日志"
    echo "  $0 logs -s app         # 查看应用日志"
    echo "  $0 test                # 测试配置"
}

# 检查 Docker 和 Docker Compose
check_prerequisites() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker 未安装"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker 服务未启动"
        exit 1
    fi

    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD="docker-compose"
    else
        log_error "Docker Compose 未安装"
        exit 1
    fi
}

# 获取 compose 文件参数
get_compose_files() {
    local env=$1

    case $env in
        prod|production)
            echo "-f docker/compose.yml"
            ;;
        dev|development)
            echo "-f docker/compose.yml -f docker/compose.dev.yml --env-file docker/.env.dev"
            ;;
        test)
            echo "-f docker/compose.yml -f docker/compose.test.yml --env-file docker/.env.test"
            ;;
        *)
            log_error "未知环境: $env (支持: prod, dev, test)"
            exit 1
            ;;
    esac
}

# 创建环境配置文件
create_env_file() {
    local env=$1
    local env_file="docker/.env"

    # 只有生产环境需要检查 .env 文件
    if [ "$env" = "prod" ] || [ "$env" = "production" ]; then
        if [ ! -f "$env_file" ]; then
            log_warn "环境配置文件不存在，将从示例创建..."
            local example_file="docker/.env.example"

            if [ -f "$example_file" ]; then
                cp "$example_file" "$env_file"
                log_info "已创建环境配置文件: $env_file (基于 $example_file)"
                log_warn "请编辑 $env_file 修改配置后重新运行"
                exit 0
            else
                log_error "找不到环境配置示例文件: $example_file"
                exit 1
            fi
        fi
    fi
}

# 部署命令
cmd_deploy() {
    log_step "部署 Service MCP 服务 (环境: $ENV)..."

    # 检查 Docker 环境
    check_prerequisites

    # 创建环境配置文件
    create_env_file "$ENV"

    # 获取 compose 文件
    local compose_files=$(get_compose_files "$ENV")

    # 添加 profile
    local profile_flag=""
    if [ -n "$PROFILE" ]; then
        profile_flag="--profile $PROFILE"
    fi

    # 构建标志
    local build_flag=""
    if [ "$BUILD" = true ]; then
        log_warn "将重新构建镜像..."
        build_flag="--build"
    fi

    # 执行部署
    $COMPOSE_CMD $compose_files $profile_flag up -d $build_flag

    log_info "部署完成！"
    log_info "使用 '$0 logs' 查看日志"
    log_info "使用 '$0 stop' 停止服务"
}

# 启动命令
cmd_start() {
    log_step "启动 Service MCP 服务 (环境: $ENV)..."

    # 检查 Docker 环境
    check_prerequisites

    # 获取 compose 文件
    local compose_files=$(get_compose_files "$ENV")

    # 添加 profile
    local profile_flag=""
    if [ -n "$PROFILE" ]; then
        profile_flag="--profile $PROFILE"
    fi

    # 执行启动
    $COMPOSE_CMD $compose_files $profile_flag up -d

    log_info "服务已启动"
    log_info "使用 '$0 logs' 查看日志"
    log_info "使用 '$0 stop' 停止服务"
}

# 停止命令
cmd_stop() {
    log_step "停止 Service MCP 服务 (环境: $ENV)..."

    # 检查 Docker 环境
    check_prerequisites

    # 获取 compose 文件
    local compose_files=$(get_compose_files "$ENV")

    # 执行停止
    if [ "$VOLUMES" = true ]; then
        log_warn "警告: 将同时删除数据卷！"
        read -p "确认删除数据卷？(y/N): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            $COMPOSE_CMD $compose_files down -v
            log_info "服务已停止，数据卷已删除"
        else
            log_info "取消操作"
            exit 0
        fi
    else
        $COMPOSE_CMD $compose_files down
        log_info "服务已停止"
    fi
}

# 更新命令
cmd_update() {
    log_step "更新 Service MCP 服务 (环境: $ENV)..."

    # 检查 Docker 环境
    check_prerequisites

    # 获取 compose 文件
    local compose_files=$(get_compose_files "$ENV")

    # 构建标志
    local build_flag=""
    if [ "$BUILD" = true ]; then
        log_warn "将重新构建镜像..."
        build_flag="--build"
    fi

    # 执行更新
    $COMPOSE_CMD $compose_files up -d $build_flag

    log_info "服务已更新"
    log_info "使用 '$0 logs' 查看日志"
}

# 日志命令
cmd_logs() {
    log_step "查看日志 (环境: $ENV)..."

    # 检查 Docker 环境
    check_prerequisites

    # 获取 compose 文件
    local compose_files=$(get_compose_files "$ENV")

    # 执行日志查看
    if [ -n "$SERVICE" ]; then
        $COMPOSE_CMD $compose_files logs -f "$SERVICE"
    else
        $COMPOSE_CMD $compose_files logs -f
    fi
}

# 测试命令
cmd_test() {
    log_step "测试配置..."

    # 检查 Docker 环境
    check_prerequisites

    # 测试 compose 配置
    log_info "测试 compose 配置..."
    if $COMPOSE_CMD -f docker/compose.yml config --quiet 2>/dev/null; then
        log_info "✓ compose.yml 配置正确"
    else
        log_error "✗ compose.yml 配置错误"
        exit 1
    fi

    # 测试环境配置
    log_info "测试环境配置..."
    if [ -f "docker/.env" ]; then
        log_info "✓ docker/.env 存在"
    else
        log_warn "⚠ docker/.env 不存在"
    fi

    log_info "测试完成！"
}

# 主逻辑
main() {
    local COMMAND=""
    local ENV="prod"
    local PROFILE=""
    local SERVICE=""
    local BUILD=false
    local VOLUMES=false

    # 解析第一个参数（命令）
    if [[ $# -gt 0 && ! "$1" =~ ^- ]]; then
        COMMAND="$1"
        shift
    fi

    # 解析其他参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--env)
                ENV="$2"
                shift 2
                ;;
            -p|--profile)
                PROFILE="$2"
                shift 2
                ;;
            -s|--service)
                SERVICE="$2"
                shift 2
                ;;
            -b|--build)
                BUILD=true
                shift
                ;;
            -v|--volumes)
                VOLUMES=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
        esac
    done

    # 切换到项目根目录
    cd "$(dirname "$0")/.."

    # 执行命令
    case $COMMAND in
        deploy)
            cmd_deploy
            ;;
        start)
            cmd_start
            ;;
        stop)
            cmd_stop
            ;;
        update)
            cmd_update
            ;;
        logs)
            cmd_logs
            ;;
        test)
            cmd_test
            ;;
        help)
            show_help
            ;;
        "")
            show_help
            ;;
        *)
            log_error "未知命令: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
