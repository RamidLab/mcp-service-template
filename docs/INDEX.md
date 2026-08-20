# 文档目录

本目录包含 Service MCP 模板的部署和运维文档。

## 文档列表

### 部署文档

| 文档                                                   | 说明          | 适用场景                        |
|------------------------------------------------------|-------------|-----------------------------|
| [LOCAL_DEPLOYMENT.md](./LOCAL_DEPLOYMENT.md)         | 本地部署指南      | 在 Windows/Linux/macOS 上本地部署 |
| [SERVER_DEPLOYMENT.md](./SERVER_DEPLOYMENT.md)       | 服务器部署指南     | 在 Ubuntu 服务器上部署             |
| [DOCKER.md](./DOCKER.md)                             | Docker 部署指南 | Docker 部署通用指南               |
| [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md) | 部署检查清单      | 部署前检查                       |

### 用户指南

| 文档                                    | 说明       | 适用用户   |
|---------------------------------------|----------|--------|
| [README.zh-CN.md](../README.zh-CN.md) | 项目说明（中文） | 所有用户   |
| [README.md](../README.md)             | 项目说明（英文） | 所有用户   |

## 快速开始

### 场景一：在 Windows 上本地部署

如果你想在 Windows 电脑上运行服务：

```powershell
# 1. 创建环境配置
cp docker\.env.example docker\.env

# 2. 编辑配置（修改数据库密码）
notepad docker\.env

# 3. 部署服务
.\docker\ctl.ps1 deploy -e prod
```

详细步骤请参考 [LOCAL_DEPLOYMENT.md](./LOCAL_DEPLOYMENT.md)。

### 场景二：在 Ubuntu 服务器上部署

如果你想在远程 Ubuntu 服务器上部署：

**第一步：测试 Docker 配置**

```powershell
# 测试你的环境是否满足部署要求
.\docker\test-docker.ps1
```

**第二步：在 Ubuntu 服务器上部署**

```bash
# 按照服务器部署指南操作
# 参考 SERVER_DEPLOYMENT.md
```

详细步骤请参考 [SERVER_DEPLOYMENT.md](./SERVER_DEPLOYMENT.md)。

### 场景三：使用 Docker 部署（通用）

如果你想使用 Docker 部署（适用于所有平台）：

```bash
# Linux/macOS
./docker/ctl.sh deploy -e prod

# Windows
.\docker\ctl.ps1 deploy -e prod

# 或者直接使用 docker compose
docker compose -f docker/compose.yml up -d
```

详细步骤请参考 [DOCKER.md](./DOCKER.md)。

## 部署前检查

在部署之前，请按照 [DEPLOYMENT_CHECKLIST.md](./DEPLOYMENT_CHECKLIST.md) 逐项检查：

- [ ] 系统要求检查
- [ ] 部署前准备
- [ ] 配置检查
- [ ] 部署测试
- [ ] 启动服务
- [ ] 部署后检查

## 文档说明

### 本地部署 vs 服务器部署

| 特性   | 本地部署                | 服务器部署                |
|------|---------------------|----------------------|
| 适用场景 | 开发、测试               | 生产环境                 |
| 操作系统 | Windows/Linux/macOS | Ubuntu 24.04         |
| 部署方式 | Docker Desktop      | Docker Engine        |
| 访问方式 | localhost           | 远程 IP/域名             |
| 文档   | LOCAL_DEPLOYMENT.md | SERVER_DEPLOYMENT.md |

## 获取帮助

如果遇到问题，请：

1. 查看相关文档
2. 提交 Issue
3. 联系项目维护者
