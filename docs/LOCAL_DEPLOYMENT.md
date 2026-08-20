# 本地部署指南

本文档介绍如何在本地计算机上部署和使用 Service MCP 服务。

## 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [详细部署步骤](#详细部署步骤)
- [配置说明](#配置说明)
- [使用服务](#使用服务)
- [数据管理](#数据管理)
- [故障排除](#故障排除)

## 系统要求

### 硬件要求

| 资源  | 最低要求  | 推荐配置  |
|-----|-------|-------|
| CPU | 2 核   | 4 核   |
| 内存  | 4 GB  | 8 GB  |
| 磁盘  | 20 GB | 50 GB |

### 软件要求

#### Windows

- **操作系统**: Windows 10/11 (64 位)
- **Docker Desktop**: 4.0+
- **PowerShell**: 5.1+ (Windows 自带)

#### Linux/macOS

- **操作系统**: Ubuntu 20.04+, macOS 10.15+
- **Docker**: 20.10+
- **Docker Compose**: v2.0+
- **Git**: 可选，用于克隆项目

## 快速开始

### 1. 安装 Docker Desktop

1. 下载 Docker Desktop: https://www.docker.com/products/docker-desktop/
2. 运行安装程序
3. 重启电脑
4. 启动 Docker Desktop

### 2. 克隆或下载项目

```powershell
# 方式一：使用 Git
git clone <your-repo-url>
cd service-mcp

# 方式二：下载 ZIP 解压后进入目录
cd service-mcp
```

### 3. 配置环境

```powershell
# 创建环境配置文件
cp docker\.env.example docker\.env

# 编辑配置文件
notepad docker\.env
```

修改以下配置：

```bash
# 必须修改！设置安全的数据库密码
DB_PG_DEFAULT_PASSWORD=your_secure_password_here

# 可选：设置 Redis 密码
# CACHE_REDIS_DEFAULT_PASSWORD=your_redis_password

# 可选：修改应用端口
APP_PORT=8001
```

### 4. 启动服务

```powershell
# 使用 PowerShell 脚本启动
.\docker\ctl.ps1 deploy -e prod

# 或者使用 docker compose 命令
docker compose -f docker\compose.yml up -d
```

### 5. 访问服务

- **MCP 服务**: http://localhost:8001/mcp
- **pgAdmin**: http://localhost:5050 (需要启用 admin profile)

## 详细部署步骤

### 步骤 1：安装 Docker Desktop

#### 下载和安装

1. 访问 Docker 官网: https://www.docker.com/products/docker-desktop/
2. 点击 "Download for Windows"
3. 运行下载的 `Docker Desktop Installer.exe`
4. 按照提示完成安装
5. 重启电脑

#### 配置 Docker Desktop

1. **启动 Docker Desktop**:
    - 从开始菜单启动
    - 等待 Docker 引擎启动完成

2. **配置资源**:
    - 点击系统托盘中的 Docker 图标
    - 选择 "Settings"
    - 进入 "Resources" → "Advanced"
    - 设置 CPU: 2 核以上
    - 设置内存: 4 GB 以上
    - 设置磁盘: 64 GB 以上

3. **启用 WSL 2 后端** (推荐):
    - 进入 "General"
    - 勾选 "Use the WSL 2 based engine"
    - 确保已安装 WSL 2

4. **配置镜像加速** (可选):
    - 进入 "Docker Engine"
    - 添加镜像源:
      ```json
      {
        "registry-mirrors": [
          "https://docker.mirrors.ustc.edu.cn",
          "https://hub-mirror.c.163.com"
        ]
      }
      ```

5. **验证安装**:
   ```powershell
   docker --version
   docker compose version
   ```

### 步骤 2：获取项目代码

```powershell
# 克隆项目
git clone <your-repo-url>
cd service-mcp
```

### 步骤 3：配置环境

```powershell
# 创建环境配置文件
cp docker\.env.example docker\.env

# 编辑配置文件
notepad docker\.env
```

#### 必须修改的配置

```bash
# 数据库密码（必须修改！）
DB_PG_DEFAULT_PASSWORD=your_secure_password_here
```

#### 可选配置

```bash
# 应用端口（默认 8001）
APP_PORT=8001

# Redis 密码（可选）
# CACHE_REDIS_DEFAULT_PASSWORD=your_redis_password

# 时区（默认 Asia/Shanghai）
TZ=Asia/Shanghai

# 数据库端口（默认 5432）
DB_PG_DEFAULT_PORT=5432

# Redis 端口（默认 6379）
CACHE_REDIS_DEFAULT_PORT=6379
```

### 步骤 4：测试配置

```powershell
# 运行 Docker 配置测试脚本
.\docker\test-docker.ps1
```

### 步骤 5：部署服务

```powershell
# 部署生产环境
.\docker\ctl.ps1 deploy -e prod

# 或者使用 docker compose
docker compose -f docker\compose.yml up -d
```

### 步骤 6：验证服务

```powershell
# 查看服务状态
docker compose -f docker\compose.yml ps

# 查看日志
.\docker\ctl.ps1 logs -e prod

# 测试服务
curl http://localhost:8001/mcp
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

### 数据目录

数据通过 bind mount 持久化到 `docker/prod_data/` 目录：

```
docker/prod_data/
├── app/
│   ├── configs/        # 应用配置
│   └── logs/           # 应用日志
├── db-pg-default/
│   └── pg_data/        # PostgreSQL 数据
├── cache-redis-default/
│   └── redis_data/     # Redis 数据
└── pgadmin/            # pgAdmin 数据（可选）
    └── data/
```

## 使用服务

### 常用命令

#### 部署服务

```powershell
# 部署生产环境
.\docker\ctl.ps1 deploy -e prod

# 部署开发环境
.\docker\ctl.ps1 deploy -e dev

# 部署生产环境 + pgAdmin
.\docker\ctl.ps1 deploy -e prod -p admin

# 强制重新构建并部署
.\docker\ctl.ps1 deploy -e prod -b
```

#### 启动/停止服务

```powershell
# 启动已停止的服务
.\docker\ctl.ps1 start -e prod

# 停止服务
.\docker\ctl.ps1 stop -e prod

# 停止服务并删除数据（危险！）
.\docker\ctl.ps1 stop -e prod -v
```

#### 更新服务

```powershell
# 更新服务
.\docker\ctl.ps1 update -e prod

# 强制重新构建并更新
.\docker\ctl.ps1 update -e prod -b
```

#### 查看日志

```powershell
# 查看所有日志
.\docker\ctl.ps1 logs -e prod

# 查看应用日志
.\docker\ctl.ps1 logs -e prod -s app

# 查看数据库日志
.\docker\ctl.ps1 logs -e prod -s db-pg-default
```

### 测试服务

```powershell
# 测试 MCP 端点
curl http://localhost:8001/mcp

# 测试 PostgreSQL
docker exec service-mcp-postgres pg_isready -U postgres

# 测试 Redis
docker exec service-mcp-redis redis-cli ping
```

## 数据管理

### 备份数据

#### 备份 PostgreSQL

```powershell
# 备份数据库
docker exec service-mcp-postgres pg_dump -U postgres service_data > backup_$(Get-Date -Format "yyyyMMdd").sql
```

#### 备份 Redis

```powershell
# 触发 Redis 备份
docker exec service-mcp-redis redis-cli BGSAVE

# 复制备份文件
docker cp service-mcp-redis:/data/dump.rdb ./redis_backup_$(Get-Date -Format "yyyyMMdd").rdb
```

### 恢复数据

#### 恢复 PostgreSQL

```powershell
# 恢复数据库
Get-Content backup_20250101.sql | docker exec -i service-mcp-postgres psql -U postgres service_data
```

#### 恢复 Redis

```powershell
# 恢复 Redis
docker cp ./redis_backup_20250101.rdb service-mcp-redis:/data/dump.rdb
docker restart service-mcp-redis
```

### 清理数据

```powershell
# 停止并删除所有数据（危险！）
.\docker\ctl.ps1 stop -e prod -v

# 清理 Docker 缓存
docker system prune -a
```

## 故障排除

### 1. Docker Desktop 无法启动

**问题**: Docker Desktop 启动失败或卡住

**解决方案**:

1. 检查虚拟化是否启用：
    - 打开任务管理器 (Ctrl+Shift+Esc)
    - 切换到"性能"选项卡
    - 查看"虚拟化"是否显示"已启用"

2. 启用 Windows 功能：
    - 控制面板 → 程序 → 启用或关闭 Windows 功能
    - 启用 "Hyper-V"
    - 启用 "适用于 Linux 的 Windows 子系统"
    - 重启电脑

3. 重新安装 Docker Desktop

### 2. 端口被占用

**问题**: 端口 8001、5432 或 6379 被占用

**解决方案**:

```powershell
# 查看端口占用
netstat -ano | findstr :8001
netstat -ano | findstr :5432
netstat -ano | findstr :6379

# 修改配置文件
notepad docker\.env
# 修改 APP_PORT、DB_PG_DEFAULT_PORT、CACHE_REDIS_DEFAULT_PORT
```

### 3. 数据库连接失败

**问题**: 无法连接到 PostgreSQL

**解决方案**:

```powershell
# 检查数据库状态
docker compose -f docker\compose.yml ps db-pg-default

# 查看数据库日志
.\docker\ctl.ps1 logs -e prod -s db-pg-default

# 测试数据库连接
docker exec -it service-mcp-postgres psql -U postgres -d service_data
```

### 4. Redis 连接失败

**问题**: 无法连接到 Redis

**解决方案**:

```powershell
# 检查 Redis 状态
docker compose -f docker\compose.yml ps cache-redis-default

# 查看 Redis 日志
.\docker\ctl.ps1 logs -e prod -s cache-redis-default

# 测试 Redis 连接
docker exec -it service-mcp-redis redis-cli ping
```

### 5. 应用无法访问

**问题**: 无法访问 http://localhost:8001

**解决方案**:

```powershell
# 检查应用状态
docker compose -f docker\compose.yml ps app

# 查看应用日志
.\docker\ctl.ps1 logs -e prod -s app

# 检查端口监听
netstat -ano | findstr :8001

# 测试本地访问
curl http://localhost:8001/mcp
```

### 6. PowerShell 执行策略错误

**问题**: 无法运行 .ps1 脚本

**解决方案**:

```powershell
# 临时允许执行
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 或者永久允许（需要管理员权限）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine
```

## 更多帮助

- 项目文档: [README.md](../README.md)
- Docker 部署: [docs/DOCKER.md](./DOCKER.md)
