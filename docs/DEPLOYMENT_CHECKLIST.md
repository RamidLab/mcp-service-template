# 部署检查清单

在部署 Service MCP 服务之前，请按照以下清单进行检查。

## 系统要求检查

### 硬件要求

- [ ] CPU: 2 核以上
- [ ] 内存: 2 GB 以上（推荐 4 GB）
- [ ] 磁盘: 20 GB 以上（推荐 50 GB）
- [ ] 网络: 稳定的网络连接

### 软件要求

- [ ] 操作系统: Ubuntu 24.04 LTS 或 Docker Desktop (Windows/macOS)
- [ ] Docker: 24.0+
- [ ] Docker Compose: v2.0+
- [ ] Git: 2.0+

## 部署前准备

### 1. 系统更新

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. 安装 Docker

```bash
# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 将用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录
# 或者运行: newgrp docker

# 验证安装
docker --version
docker compose version
```

### 3. 安装 Git

```bash
sudo apt install -y git
git --version
```

### 4. 克隆项目

```bash
git clone <your-repo-url>
cd service-mcp
```

## 配置检查

### 1. 创建环境配置

```bash
cp docker/.env.example docker/.env
```

### 2. 修改配置

编辑 `docker/.env` 文件：

- [ ] 设置安全的数据库密码: `DB_PG_DEFAULT_PASSWORD`
- [ ] 可选：设置 Redis 密码: `CACHE_REDIS_DEFAULT_PASSWORD`
- [ ] 可选：修改应用端口: `APP_PORT`
- [ ] 可选：修改时区: `TZ`

### 3. 检查端口

确保以下端口可用：

- [ ] 8001 (MCP 服务)
- [ ] 5432 (PostgreSQL)
- [ ] 6379 (Redis)
- [ ] 5050 (pgAdmin，可选)

```bash
# 检查端口占用
sudo ss -tuln | grep -E ":(8001|5432|6379|5050) "
```

## 部署测试

### 1. 验证配置

```bash
# 测试 Docker 配置
./docker/test-docker.sh

# 验证 compose 文件
docker compose -f docker/compose.yml config --quiet
```

## 启动服务

### 1. 启动服务

```bash
./docker/ctl.sh deploy -e prod
```

### 2. 检查服务状态

```bash
# 查看服务状态
docker compose -f docker/compose.yml ps

# 查看服务日志
docker compose -f docker/compose.yml logs -f
```

### 3. 验证服务

```bash
# 测试应用服务
curl http://localhost:8001/mcp

# 测试 PostgreSQL
docker exec service-mcp-postgres pg_isready -U postgres

# 测试 Redis
docker exec service-mcp-redis redis-cli ping
```

## 部署后检查

### 1. 服务状态

- [ ] 所有服务都在运行
- [ ] 没有错误日志
- [ ] 服务可以正常访问

### 2. 数据持久化

- [ ] 数据目录已创建
- [ ] 数据文件有正确的权限
- [ ] 备份策略已配置

### 3. 安全检查

- [ ] 默认密码已修改
- [ ] 防火墙已配置
- [ ] 端口访问已限制
- [ ] Redis 密码已设置（可选）

### 4. 监控配置

- [ ] 日志监控已配置
- [ ] 资源监控已配置
- [ ] 告警通知已配置（可选）

## 常见问题检查

### 1. 端口冲突

```bash
# 检查端口占用
sudo ss -tuln | grep :8001

# 修改端口配置
nano docker/.env
```

### 2. 权限问题

```bash
# 检查用户组
groups

# 添加到 docker 组
sudo usermod -aG docker $USER
```

### 3. 磁盘空间

```bash
# 检查磁盘空间
df -h

# 清理 Docker 缓存
docker system prune -a
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
```

## 备份和恢复

### 备份数据

```bash
# 备份 PostgreSQL
docker exec service-mcp-postgres pg_dump -U postgres service_data > backup_$(date +%Y%m%d).sql

# 备份 Redis
docker exec service-mcp-redis redis-cli BGSAVE
docker cp service-mcp-redis:/data/dump.rdb ./redis_backup_$(date +%Y%m%d).rdb
```

### 恢复数据

```bash
# 恢复 PostgreSQL
cat backup_20250101.sql | docker exec -i service-mcp-postgres psql -U postgres service_data

# 恢复 Redis
docker cp ./redis_backup_20250101.rdb service-mcp-redis:/data/dump.rdb
docker restart service-mcp-redis
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

## 相关文档

- [README.zh-CN.md](../README.zh-CN.md) - 项目说明
- [DOCKER.md](./DOCKER.md) - Docker 部署文档
- [SERVER_DEPLOYMENT.md](./SERVER_DEPLOYMENT.md) - 服务器部署文档
- [LOCAL_DEPLOYMENT.md](./LOCAL_DEPLOYMENT.md) - 本地部署文档

## 获取帮助

如果遇到问题，请：

1. 查看本文档的故障排除部分
2. 查看相关文档
3. 提交 Issue
