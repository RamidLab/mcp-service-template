# 服务器部署指南

本文档详细介绍如何在 Ubuntu 24.04 服务器上部署 Service MCP 服务。

## 目录

- [系统要求](#系统要求)
- [部署前检查](#部署前检查)
- [安装步骤](#安装步骤)
- [配置说明](#配置说明)
- [验证部署](#验证部署)
- [常见问题](#常见问题)
- [故障排除](#故障排除)

## 系统要求

### 硬件要求

| 资源  | 最低要求   | 推荐配置    |
|-----|--------|---------|
| CPU | 2 核    | 4 核     |
| 内存  | 2 GB   | 4 GB    |
| 磁盘  | 20 GB  | 50 GB   |
| 网络  | 1 Mbps | 10 Mbps |

### 软件要求

- **操作系统**: Ubuntu 24.04 LTS
- **Docker**: 24.0+
- **Docker Compose**: v2.0+
- **Git**: 2.0+

## 部署前检查

### 方法一：使用测试脚本（推荐）

```bash
# 给脚本添加执行权限
chmod +x docker/test-docker.sh

# 运行测试
./docker/test-docker.sh
```

### 方法二：手动检查

在 Ubuntu 24.04 服务器上运行以下命令：

```bash
# 检查系统版本
cat /etc/os-release | grep -E "^(NAME|VERSION|ID)="

# 检查系统资源
echo "=== CPU ==="
nproc
echo "=== 内存 ==="
free -h
echo "=== 磁盘 ==="
df -h /

# 检查必要命令
for cmd in docker git curl; do
    if command -v $cmd &> /dev/null; then
        echo "✓ $cmd: $($cmd --version | head -1)"
    else
        echo "✗ $cmd 未安装"
    fi
done

# 检查端口
for port in 8001 5432 6379; do
    if ! ss -tuln | grep -q ":$port "; then
        echo "✓ 端口 $port 可用"
    else
        echo "⚠ 端口 $port 已被占用"
    fi
done
```

## 安装步骤

### 步骤 1：安装 Docker

```bash
# 更新系统
sudo apt update
sudo apt upgrade -y

# 安装依赖
sudo apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 添加 Docker 官方 GPG 密钥
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# 添加 Docker 仓库
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装 Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 将当前用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录以使组生效
# 或者运行: newgrp docker

# 验证安装
docker --version
docker compose version
```

### 步骤 2：安装 Git

```bash
# 安装 Git
sudo apt install -y git

# 验证安装
git --version
```

### 步骤 3：克隆项目

```bash
# 克隆项目
git clone <your-repo-url>

# 进入项目目录
cd service-mcp
```

### 步骤 4：配置环境

```bash
# 创建环境配置文件
cp docker/.env.example docker/.env

# 编辑配置文件
nano docker/.env
```

### 步骤 5：修改配置

编辑 `docker/.env` 文件，修改以下配置：

```bash
# 必须修改！设置安全的数据库密码
DB_PG_DEFAULT_PASSWORD=your_secure_password_here

# 可选：设置 Redis 密码
CACHE_REDIS_DEFAULT_PASSWORD=your_redis_password

# 可选：修改应用端口
APP_PORT=8001

# 可选：修改时区
TZ=Asia/Shanghai
```

### 步骤 6：部署服务

```bash
# 使用管理脚本部署（推荐）
./docker/ctl.sh deploy -e prod

# 或者直接使用 docker compose
docker compose -f docker/compose.yml up -d
```

## 配置说明

### 环境变量

| 变量名                            | 说明            | 默认值          | 是否必须  |
|--------------------------------|---------------|-----------------|-------|
| `TZ`                           | 时区            | `Asia/Shanghai` | 否     |
| `APP_PORT`                     | 应用端口          | `8001`          | 否     |
| `DB_PG_DEFAULT_USER`           | PostgreSQL 用户 | `postgres`      | 否     |
| `DB_PG_DEFAULT_PASSWORD`       | PostgreSQL 密码 | -               | **是** |
| `DB_PG_DEFAULT_DB`             | 数据库名          | `service_data`  | 否     |
| `DB_PG_DEFAULT_PORT`           | PostgreSQL 端口 | `5432`          | 否     |
| `CACHE_REDIS_DEFAULT_PORT`     | Redis 端口      | `6379`          | 否     |
| `CACHE_REDIS_DEFAULT_PASSWORD` | Redis 密码      | -               | 否     |

### 端口说明

| 端口 | 服务         | 说明        |
|------|------------|-----------|
| 8001 | MCP 服务     | 主服务端点     |
| 5432 | PostgreSQL | 数据库       |
| 6379 | Redis      | 缓存        |
| 5050 | pgAdmin    | 数据库管理（可选） |

## 验证部署

### 检查服务状态

```bash
# 查看所有服务状态
docker compose -f docker/compose.yml ps

# 查看服务日志
docker compose -f docker/compose.yml logs -f

# 查看特定服务日志
docker compose -f docker/compose.yml logs -f app
docker compose -f docker/compose.yml logs -f db-pg-default
docker compose -f docker/compose.yml logs -f cache-redis-default
```

### 测试服务连接

```bash
# 测试应用服务
curl http://localhost:8001/mcp

# 测试 PostgreSQL
docker exec service-mcp-postgres pg_isready -U postgres

# 测试 Redis
docker exec service-mcp-redis redis-cli ping
```

### 访问服务

- **MCP 服务**: http://your-server-ip:8001/mcp
- **pgAdmin**（如果启用）: http://your-server-ip:5050

## 常见问题

### 1. 端口被占用

```bash
# 检查端口占用
sudo ss -tuln | grep :8001
sudo ss -tuln | grep :5432
sudo ss -tuln | grep :6379

# 修改端口配置
nano docker/.env
# 修改 APP_PORT、DB_PG_DEFAULT_PORT、CACHE_REDIS_DEFAULT_PORT
```

### 2. 权限问题

```bash
# 将用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录
# 或者运行: newgrp docker

# 验证权限
docker ps
```

### 3. 磁盘空间不足

```bash
# 检查磁盘空间
df -h

# 清理 Docker 缓存
docker system prune -a

# 清理未使用的镜像
docker image prune -a
```

### 4. 内存不足

```bash
# 检查内存
free -h

# 添加 swap 空间
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 永久启用 swap
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 5. 防火墙问题

```bash
# 检查防火墙状态
sudo ufw status

# 开放端口
sudo ufw allow 8001/tcp
sudo ufw allow 5432/tcp
sudo ufw allow 6379/tcp

# 重新加载防火墙
sudo ufw reload
```

## 故障排除

### 1. 服务启动失败

```bash
# 查看详细日志
docker compose -f docker/compose.yml logs app

# 检查容器状态
docker compose -f docker/compose.yml ps -a

# 进入容器调试
docker exec -it service-mcp-app bash
```

### 2. 数据库连接失败

```bash
# 检查数据库状态
docker compose -f docker/compose.yml ps db-pg-default

# 查看数据库日志
docker compose -f docker/compose.yml logs db-pg-default

# 测试数据库连接
docker exec -it service-mcp-postgres psql -U postgres -d service_data
```

### 3. Redis 连接失败

```bash
# 检查 Redis 状态
docker compose -f docker/compose.yml ps cache-redis-default

# 查看 Redis 日志
docker compose -f docker/compose.yml logs cache-redis-default

# 测试 Redis 连接
docker exec -it service-mcp-redis redis-cli ping
```

### 4. 应用无法访问

```bash
# 检查应用日志
docker compose -f docker/compose.yml logs app

# 检查端口监听
sudo ss -tuln | grep :8001

# 测试本地访问
curl http://localhost:8001/mcp

# 测试远程访问
curl http://your-server-ip:8001/mcp
```

## 更新部署

```bash
# 拉取最新代码
git pull

# 重新构建并部署
./docker/ctl.sh update -e prod -b

# 清理旧镜像
docker image prune -f
```

## 安全建议

1. **修改默认密码**: 必须修改 `docker/.env` 中的数据库密码
2. **限制端口访问**: 使用防火墙限制外部访问
3. **启用 Redis 密码**: 设置 `CACHE_REDIS_DEFAULT_PASSWORD`
4. **使用 HTTPS**: 配置反向代理（如 Nginx）启用 HTTPS
5. **定期备份**: 配置定期数据库备份策略
6. **监控日志**: 定期检查应用和数据库日志
7. **更新系统**: 定期更新系统和 Docker

## 更多帮助

- 项目文档: [README.zh-CN.md](../README.zh-CN.md)
- Docker 部署: [DOCKER.md](./DOCKER.md)
