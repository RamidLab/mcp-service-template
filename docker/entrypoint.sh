#!/bin/bash
set -e

# 颜色输出
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

# 等待服务就绪
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    local max_retries=${4:-30}
    local retry_interval=${5:-2}

    log_info "等待 ${service_name} 服务就绪 (${host}:${port})..."

    for i in $(seq 1 $max_retries); do
        if curl -s -o /dev/null -w "%{http_code}" "http://${host}:${port}" >/dev/null 2>&1 || \
           nc -z "$host" "$port" >/dev/null 2>&1 || \
           bash -c "echo >/dev/tcp/${host}/${port}" >/dev/null 2>&1; then
            log_info "${service_name} 服务已就绪"
            return 0
        fi
        log_warn "等待 ${service_name} 服务... (${i}/${max_retries})"
        sleep $retry_interval
    done

    log_error "${service_name} 服务连接超时"
    return 1
}

# 自动创建数据库（如果不存在）
ensure_database() {
    local engine=$1
    local host=$2
    local port=$3
    local user=$4
    local password=$5
    local db=$6

    if [ -z "$db" ]; then
        log_warn "未配置 ${engine} 数据库名，跳过自动创建"
        return 0
    fi

    log_info "检查 ${engine} 数据库 ${db} 是否存在..."
    python3 /app/create_db.py "$engine" \
        --host "$host" \
        --port "$port" \
        --user "$user" \
        --password "$password" \
        --db "$db"
}

# 等待数据库服务
wait_for_databases() {
    # 等待 PostgreSQL
    if [ -n "$DB_PG_DEFAULT_HOST" ]; then
        wait_for_service "$DB_PG_DEFAULT_HOST" "${DB_PG_DEFAULT_PORT:-5432}" "PostgreSQL"
        ensure_database "postgresql" \
            "$DB_PG_DEFAULT_HOST" \
            "${DB_PG_DEFAULT_PORT:-5432}" \
            "${DB_PG_DEFAULT_USER}" \
            "${DB_PG_DEFAULT_PASSWORD}" \
            "${DB_PG_DEFAULT_DB}"
    fi

    # 等待 Redis
    if [ -n "$CACHE_REDIS_DEFAULT_HOST" ]; then
        wait_for_service "$CACHE_REDIS_DEFAULT_HOST" "${CACHE_REDIS_DEFAULT_PORT:-6379}" "Redis"
    fi

    # 等待 MySQL（如果配置了）
    if [ -n "$DB_MYSQL_DEFAULT_HOST" ]; then
        wait_for_service "$DB_MYSQL_DEFAULT_HOST" "${DB_MYSQL_DEFAULT_PORT:-3306}" "MySQL"
        ensure_database "mysql" \
            "$DB_MYSQL_DEFAULT_HOST" \
            "${DB_MYSQL_DEFAULT_PORT:-3306}" \
            "${DB_MYSQL_DEFAULT_USER:-root}" \
            "${DB_MYSQL_DEFAULT_PASSWORD}" \
            "${DB_MYSQL_DEFAULT_DB}"
    fi
}

# 主逻辑
main() {
    log_info "启动 Service MCP 服务器..."
    log_info "环境: ${MCP_ENV:-dev}"
    log_info "传输模式: ${1:-streamable-http}"

    # 等待依赖服务就绪
    if [ "${WAIT_FOR_SERVICES:-true}" = "true" ]; then
        wait_for_databases
    fi

    # 确保配置目录存在
    mkdir -p /app/configs /app/logs

    # 启动应用
    log_info "启动 MCP 服务器..."
    exec service-mcp "$@"
}

# 入口点
# 如果传入的是命令而不是子命令，直接执行
if [ "$1" = "bash" ] || [ "$1" = "sh" ]; then
    exec "$@"
fi

# 否则启动 MCP 服务器
main "$@"
