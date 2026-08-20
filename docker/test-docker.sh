#!/bin/bash
set -e

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# ── 测试 Docker 配置 ──────────────────────────────────────────────────────────
test_docker_config() {
    log_info "测试 Docker 配置..."

    # 检查必要文件
    local files=(
        "Dockerfile"
        "docker/compose.yml"
        "docker/entrypoint.sh"
        "docker/.env.example"
    )

    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            log_info "✓ $file 存在"
        else
            log_error "✗ $file 不存在"
            return 1
        fi
    done

    # 检查 Dockerfile 语法
    log_info "检查 Dockerfile 语法..."
    if docker build --check . 2>/dev/null || true; then
        log_info "✓ Dockerfile 语法正确"
    else
        log_warn "⚠ 无法验证 Dockerfile 语法"
    fi

    # 检查 compose 文件语法
    log_info "检查 compose 文件语法..."
    if docker compose -f docker/compose.yml config --quiet 2>/dev/null; then
        log_info "✓ compose.yml 语法正确"
    else
        log_error "✗ compose.yml 语法错误"
        return 1
    fi

    log_info "Docker 配置测试完成"
}

# ── 测试环境配置 ──────────────────────────────────────────────────────────────
test_env_config() {
    log_info "测试环境配置..."

    # 检查环境变量文件
    if [ -f "docker/.env" ]; then
        log_info "✓ docker/.env 存在"

        # 检查必要的环境变量
        local required_vars=(
            "DB_PG_DEFAULT_USER"
            "DB_PG_DEFAULT_PASSWORD"
            "DB_PG_DEFAULT_DB"
        )

        for var in "${required_vars[@]}"; do
            if grep -q "^${var}=" docker/.env; then
                log_info "✓ $var 已配置"
            else
                log_warn "⚠ $var 未配置"
            fi
        done
    else
        log_warn "⚠ docker/.env 不存在（将从示例创建）"
    fi
}

# ── 测试 Docker 构建 ──────────────────────────────────────────────────────────
test_docker_build() {
    log_info "测试 Docker 构建..."

    # 尝试构建镜像
    if docker build -t service-mcp-test . 2>&1 | tail -5; then
        log_info "✓ Docker 镜像构建成功"

        # 清理测试镜像
        docker rmi service-mcp-test 2>/dev/null || true
    else
        log_error "✗ Docker 镜像构建失败"
        return 1
    fi
}

# ── 主函数 ────────────────────────────────────────────────────────────────────
main() {
    log_info "开始 Docker 配置测试..."
    echo ""

    # 切换到项目根目录
    cd "$(dirname "$0")/.."

    # 运行测试
    test_docker_config
    echo ""

    test_env_config
    echo ""

    # 询问是否测试构建
    read -p "是否测试 Docker 构建？(y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        test_docker_build
    else
        log_info "跳过 Docker 构建测试"
    fi

    echo ""
    log_info "测试完成！"
    log_info "使用以下命令启动服务："
    log_info "  ./docker/ctl.sh -a deploy -e prod"
}

main "$@"
