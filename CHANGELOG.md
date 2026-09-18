# 更新日志

本文件记录项目中所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，并遵循 [语义化版本控制](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- **鉴权加固（mcp_perm）**: async 工具装饰后 wrapper 保持 async 语义，修复协程体内读不到
  `_current_perm_scope`（OWN 数据范围静默失效）与后台任务校验误拒问题；admin 模式下
  AuthContext 缺失 fail-closed 拒绝，tool 模式维持无鉴权全量放行。
- **三级数据范围可见性引擎**: `auth/context.py` 新增 `scope_visibility_where()`（平台/部门/个人
  服务端强制过滤）与 `current_team_id()`；`utils/enums.py` 新增 `DataScope`、`PublishStatus`
  （发布审核门槛：PENDING/REJECTED 仅归属者可见，NULL 视为已审核）。
- 新增测试：`tests/test_auth_failclosed.py`。

### Changed

- auth 中间件移除 `new_access_token` 死分支；`AuthContext` 新增 `team_ids` 字段。

## [0.2.0] - 2026-08-26

### Added

- **通用基础设施**:
  - `utils/rate_limiter.py`: 按 key 限速器（`KeyRateLimiter` + 全局单例，随机抖动）。
  - `utils/spill.py`: 大结果溢出（`LargeResultWriter` + `sweep_spill_dir`，原子写入 + 启动清扫）。
  - `utils/cron.py`: 标准 5 段 cron 表达式解析（`CronExpression`）。
  - `utils/export.py`: BOM 安全 CSV 导出助手（`csv_bom` / `rows_to_csv`）。
  - `task/`: 通用后台任务包（`TaskManager` 生命周期管理 + `TaskScheduler` cron 调度，runner 注入式）。
  - `tools/export_tools.py`: CSV 导出示例工具 `export_products_csv`（复用动态 Filter + `rows_to_csv`）。
  - 新增单元测试：`test_rate_limiter.py` / `test_spill.py` / `test_cron.py` / `test_task_manager.py` / `test_export.py`。

## [0.1.1] - 2026-08-20

### Added

- **JWT Token 存储与自动续期**: [`AuthContext`](service_mcp/auth/context.py) 新增 `access_token` 字段，[`JWTAuthMiddleware`](service_mcp/auth/middleware.py) 支持后端返回 `new_access_token` 自动续期。

### Changed

- **日志抑制**: [`server.py`](service_mcp/server.py) 屏蔽 `uvicorn`、`httpx`、`httpcore`、`aiohttp` 请求日志。

## [0.1.0] - 2026-08-14

### Added

- `server.py`: streamable-http 模式添加 SIGTERM / SIGINT 信号处理，容器环境下优雅退出。
- `server.py`: 启动时抑制 uvicorn / httpx / httpcore / aiohttp 请求日志噪音。
- `auth/context.py`: 新增 `set_auth_context()`（测试注入）、`current_owner()`（当前操作者归属）、`visible_owners()`（多用户数据隔离）。
- `auth/__init__.py`: 导出新增的三个认证辅助函数。
- `models/orm/base.py`: 新增 `Utf8JSON` TypeDecorator，JSON 列存储时保留中文可读（`ensure_ascii=False`）。
- `models/orm/base.py`: `Base.created_by` 类型从 `String(50)` 改为 `Integer`，与 `AuthContext.user_id` 一致。
- `handlers/base_handlers.py`: 新增 `owner_visibility_where()` 和 `apply_owner_visibility()`，支持按 owner 隔离查询。
- `handlers/cleanup.py`: 通用关联数据清除框架（`CleanupRule` / `register_cleanup` / CASCADE / ORPHAN 策略 + 前置钩子）。
- `utils/crypto.py`: Fernet 对称加密工具（`encrypt_password` / `decrypt_password`，`enc:` 前缀密文，无密钥时退化为明文）。
- `config.py`: 新增 `encryption_key` 配置字段（`MCP_ENCRYPTION_KEY` 环境变量）。
- `pyproject.toml`: 新增 `cryptography>=50.0.0` 依赖。
- `docs/`: 新增 INDEX.md、LOCAL_DEPLOYMENT.md、SERVER_DEPLOYMENT.md、DEPLOYMENT_CHECKLIST.md 部署文档。
- `docker/`: 新增 test-docker.sh / test-docker.ps1 Docker 配置测试脚本。

## [0.0.1] - 2026-08-13

### Added

- 初始化通用 FastMCP + SQLAlchemy CRUD 服务模板（由基金净值 MCP 服务蒸馏）：注册表驱动 CRUD、FK code 自动解析、占位自动创建、孤儿标记、动态 Filter/Search、多传输 CLI、Docker 部署、改名脚本。
- 示例实体 Product / ProductPrice 端到端实现，演示全部核心模式（含价格冲突版本化、复合键删除）。

[Unreleased]: https://github.com/RamidLab/mcp-service-template/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/RamidLab/mcp-service-template/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/RamidLab/mcp-service-template/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/RamidLab/mcp-service-template/releases/tag/v0.1.0
[0.0.1]: https://github.com/RamidLab/mcp-service-template/releases/tag/v0.0.1