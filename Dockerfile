# 基础镜像
FROM python:3.12-slim-bookworm AS base

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 依赖安装阶段
FROM base AS deps

WORKDIR /app

# 安装 uv 包管理器
RUN pip install uv

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装生产依赖（不安装开发依赖）
RUN uv sync --frozen --no-dev --no-install-project

# 应用构建阶段
FROM deps AS build

# 复制源代码
COPY . .

# 安装项目本身
RUN uv sync --frozen --no-dev && \
    uv pip install --force-reinstall --no-deps redis==7.4.0 hiredis

# 生产镜像
FROM python:3.12-slim-bookworm AS production

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    MCP_ENV=prod \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8001 \
    MCP_CONFIG_PRIORITY=env_first

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/configs /app/logs

# 从构建阶段复制虚拟环境
COPY --from=build /app/.venv /app/.venv

# 复制应用代码
COPY --from=build /app/service_mcp /app/service_mcp
COPY --from=build /app/pyproject.toml /app/

# 复制启动脚本和辅助工具
COPY docker/entrypoint.sh /app/entrypoint.sh
COPY docker/create_db.py /app/create_db.py
RUN apt-get update && apt-get install -y --no-install-recommends dos2unix \
    && dos2unix /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh \
    && apt-get purge -y dos2unix \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -s http://localhost:${MCP_PORT}/mcp > /dev/null 2>&1 || exit 1

# 暴露端口
EXPOSE ${MCP_PORT}

# 设置入口点
ENTRYPOINT ["/app/entrypoint.sh"]

# 默认命令
CMD ["streamable-http"]
