# 更新日志

本文件记录项目中所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，并遵循 [语义化版本控制](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.4.1] - 2026-11-04

### Security

- **写侧缺身份按模式分叉**（[`handlers/ownership.py`](service_mcp/handlers/ownership.py)）：
  `admin` 模式（`MCP_AUTH_MODE=admin`）下没有 AuthContext 时，带 `data_scope` 列的模型一律拒写
  （`AUTH_INSUFFICIENT_SCOPE`）——装饰器那层 fail-closed 只挡工具调用，进程内宿主与"未恢复身份
  快照的后台任务"直接调 handler 绕得开它。`tool` 模式口径不变（无身份即全量，采集照常）。
  判"要不要拒"的口径收敛到唯一一处 `auth.config.is_admin_mode`，装饰器与写侧不再各读各的环境变量。
  没有归属列的模型不受影响，一条用例把这条豁免也钉住（否则下一位作者会把示例域写死）。
- **越权与"记录不存在"合并成一句话**（[`handlers/base_handlers.py`](service_mcp/handlers/base_handlers.py)）：
  此前收敛生效时回的是"未找到 id=N 的记录"，那是对存在性的**错误断言**——调用者信了就会去新建，
  撞唯一键的那一刻反而把"这行确实存在"暴露出去。现在可见性条件一旦施加，两句合成一句
  「不存在，或不在你的数据范围内」，错误码不变（`RECORD_NOT_FOUND`）；未施加收敛（tool 模式/无归属列）
  时没有歧义，仍回"未找到"。新增用例先归一 id 再逐字比较两句，并断言"不可见"三字不得出现——
  实测过变异：把不可见的行改成另一套文案，用例立刻红。

## [0.4.0] - 2026-11-04

### Changed

- **示例域对齐**: Product / ProductPrice 字段改为与同族 backend/frontend demo 商品契约一致
  （`code`/`name`/`category`/`price`/`stock`/`is_active`/`remark`；价格表对外 `code` + `price_date` + `price`）。
  新增 `ProductCategory`（实物商品/虚拟商品/服务），删除金融风枚举与字段
  （`ProductType`/`ProductStatus`/`ProductDataSource`、`acc_price`/`daily_return_rate`/`data_source` 等）。
  教学模式保留：FK code 解析、复合唯一键 `(product_id, price_date, version)`、版本冲突、异常标记、软删、占位自动创建。
- **文档与脚本**: README 去除公司业务谱系表述；AGENTS 示例字段同步并修正 middleware 说明；
  `scripts/rename_project.py` 默认 dry-run、加 `--write` 才落盘，SKIP_FILES 包含脚本自身；
  `pyproject.toml` 移除未使用的 `booktype`，redis 约束对齐家族写法。

### Fixed

- **非终端环境下控制台日志改走纯文本一行一条**（[`utils/log.py`](service_mcp/utils/log.py)）：rich 把一条
  记录拆成带边框的多行并按列宽折行，重定向到文件/管道后没法按行 grep，Windows 上还要为渲染付 CPU。
  现在 `configure_logging` 按 `sys.stdout.isatty()` 选处理器（交互终端照旧 rich），并新增
  `demote_console_rendering()`——`configure_logging` 只清 root 的处理器，管不到 FastMCP 那个 logger
  自带的那一路，[`server.py`](service_mcp/server.py) 启动时对它补一次替换，交互终端上行为不变。
- **迁移脚本的数据库连接串只报掩码后的口令位**（[`scripts/_migration_common.py`](scripts/_migration_common.py)）：
  预演是**只读**动作，正因为它只读，人才会放松地去截屏、贴日志、转进会话记录，而脚本头一行原来打成
  原文 DSN。现在统一走 `masked_url`：**只遮口令**，方言/用户/主机/库名照旧保留（那是运维判断
  "我连的是哪台库"所需的信息）；另加一条扫源用例，把 `scripts/*.py` 里任何把 `{url}` 裸着打进
  print 的行判红，免得只修这次跑到的那一个脚本。
- **权限发现补登记导出工具模块**（[`auth/discovery.py`](service_mcp/auth/discovery.py)）：`get_all_permissions`
  只扫手写的 `_TOOL_MODULES`，`export_tools` 漏在里面——工具照旧能用、超管照旧能调，但它声明的
  权限码永远不进 `/permissions`，后端 RBAC 里就没有这一行，除超管以外的人一个都拿不到。
  新增 [`tests/test_auth_discovery.py`](tests/test_auth_discovery.py) 逐模块扫工具包，把"声明过码的模块
  必须都在扫描清单里"与"下发的码要能查到资源名/操作名"钉成可红的断言。

### Security

- **写侧接上读侧同一份三级可见性**（[`handlers/base_handlers.py`](service_mcp/handlers/base_handlers.py)）：
  此前 `scope_visibility_where()` 只作用于查询，写路径按主键直改——任何持有更新/删除权限码的调用方
  都能改写他人 `personal` 行。现在 [`update_handlers.py`](service_mcp/handlers/update_handlers.py) 与
  [`delete_handlers.py`](service_mcp/handlers/delete_handlers.py) 的单条定位统一带可见性条件（删除路径
  不再自带一份主键查询），批量更新先把 id 收敛到可见子集再写；越权与"记录不存在"共用同一条报错，
  批量提示也不区分两者，否则写接口就成了探测他人行是否存在的信道。
- **新增行按身份落归属**（[`add_handlers.py`](service_mcp/handlers/add_handlers.py)）：有 AuthContext 且未表态
  档位时默认 `personal` + 当前用户，`team` 档取调用者自属部门（无部门只告警、不臆造），`platform` 档
  仍需显式表态；`current_team_id()` 从死代码接进写侧。无鉴权上下文（tool 模式/后台任务）口径不变，
  示例域模型不带归属列因此不受影响。新增 [`tests/test_write_scope.py`](tests/test_write_scope.py) 钉住
  越权被拒、本人放行、tool 模式全量、归属注入四条口径。
- **归属档位落点强制**（[`handlers/ownership.py`](service_mcp/handlers/ownership.py)）：上一条保留了调用方
  送来的任何 `data_scope` 值，于是任何登录用户写 `data_scope="platform"` 就能把行落进全员共享档。
  现在新增路径在归属注入之后统一过四条判据——档位值只认 `DataScope` 词表（档位列是裸字符串、无 CHECK
  约束，读侧只认字面量，放过不认识的值就是"写得进、谁都读不到"）、落 `platform` 需该实体的治理权限码、
  `personal` 的 `owner_id` 只能是调用者本人、`team` 的 `team_id` 只能是 `ctx.team_ids` 里的部门
  （跨部门落档要治理码，读侧"看得见全部部门"不算授权）。治理码不写死字面量：
  `handlers/ownership.GOVERNANCE_RESOURCES` 按表名登记**资源码**，完整码经
  `auth.decorator.build_perm_code` 现拼（前缀由那一处持有，`@mcp_perm` 与判据同源不分叉），
  登记的码一并随 `/permissions` 下发——RBAC 只灌那一枚清单，不下发就没人能被授予。
  实体未登记时平台档只剩超管写得（fail-closed，宁可挡住也不给一把不存在的码放行）；
  无鉴权上下文与不带 `data_scope` 列的模型口径不变。新增/批量新增的业务拒绝改为按自带错误码返回
  （`TOOL_INVALID_PARAMS` / `AUTH_INSUFFICIENT_SCOPE`），不再一律塌成 `FAIL`。

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

- 初始化通用 FastMCP + SQLAlchemy CRUD 服务模板（历史条目：由基金净值 MCP 服务蒸馏，现已中性化）：
  注册表驱动 CRUD、FK code 自动解析、占位自动创建、孤儿标记、动态 Filter/Search、多传输 CLI、
  Docker 部署、改名脚本。
- 示例实体 Product / ProductPrice 端到端实现，演示全部核心模式（含价格冲突版本化、复合键删除）。
  历史字段名（product_code 等）仅出现在本历史条目，当前代码契约已对齐 backend/frontend。

[Unreleased]: ./CHANGELOG.md
[0.3.0]: ./CHANGELOG.md
[0.2.0]: ./CHANGELOG.md
[0.1.1]: ./CHANGELOG.md
[0.1.0]: ./CHANGELOG.md
[0.0.1]: ./CHANGELOG.md
