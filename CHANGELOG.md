# 更新日志

本文件记录项目中所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，并遵循 [语义化版本控制](https://semver.org/lang/zh-CN/)。

## [0.3.0] - 2026-09-18

### Added

- **鉴权加固（mcp_perm）**: async 工具装饰后 wrapper 保持 async 语义，修复协程体内读不到
  `_current_perm_scope`（OWN 数据范围静默失效）与后台任务校验误拒问题；admin 模式下
  AuthContext 缺失 fail-closed 拒绝，tool 模式维持无鉴权全量放行。
- **三级数据范围可见性引擎**: `auth/context.py` 新增 `scope_visibility_where()`（平台/部门/个人
  服务端强制过滤）与 `current_team_id()`；`utils/enums.py` 新增 `DataScope`、`PublishStatus`
  （发布审核门槛：PENDING/REJECTED 仅归属者可见，NULL 视为已审核）。
- **父实体可见性注册表**: `models/orm.PARENT_ENTITY_MAP` 声明（子表 → (父实体, 外键列)），
  无自身归属列的子表查询按“父实体可见”过滤，孤儿行（外键空/父缺失）豁免保持可见。
- **软删行默认隐藏**: 列表/搜索路径对带 `is_deleted` 列的模型自动叠加 `is_deleted == False`。
- **ToolError 业务失败收口**: `error/exceptions.py` 新增 `ToolError`（ValueError 子类，携带业务
  `Errcode`）；`Errcode` 新增 `BUSINESS_FAILED`；handler 层定位/解析类可预期失败改为抛
  `ToolError`（继承 ValueError，兼容既有兜底断言）。
- 新增测试：`tests/test_auth_failclosed.py` / `tests/test_scope_visibility.py` /
  `tests/test_tool_error.py`。

- **工具层收口与批量上限**: crud_factory 六个生成工具统一 try/except 把 `ToolError` 收口为
  `UtilResponse` 业务响应（绝不 500 化）；批量变更工具单次最大 `MAX_BATCH_SIZE=200` 条。
- **工具注解预设**: `tools/annotations.py`（READ_ONLY / WRITE_IDEMPOTENT / WRITE_MUTATING /
  WRITE_DESTRUCTIVE），全面接入 CRUD 工厂与 query/dict/basic/export 工具。
### Changed

- auth 中间件移除 `new_access_token` 死分支；`AuthContext` 新增 `team_ids` 字段。
- cron 字段解析改静态方法；限速器单例改局部引用写入；调度器 `update_next_run` 转公开 API。
- README / AGENTS.md 同步更新（鉴权与数据范围模式、错误收口说明）。

### Fixed

- `dict_meta` 补 `mcp_perm`（配置查看权限码）：admin 模式不再对实体元数据读取裸放行。

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

[Unreleased]: https://github.com/RamidLab/mcp-service-template/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/RamidLab/mcp-service-template/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/RamidLab/mcp-service-template/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/RamidLab/mcp-service-template/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/RamidLab/mcp-service-template/releases/tag/v0.1.0
[0.0.1]: https://github.com/RamidLab/mcp-service-template/releases/tag/v0.0.1