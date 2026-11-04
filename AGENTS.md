# AGENTS.md — Service MCP 模板

## 项目概览

通用 MCP 服务模板（FastMCP + SQLAlchemy async + Pydantic v2 + Typer CLI），含示例实体
Product / ProductPrice，演示完整 CRUD + 外键解析 + 动态 Filter/Search 链路。
示例域字段与同族 `backend/apps/demo_module`、`frontend` demo 商品契约对齐。

- **Python**: 3.12+ 必须
- **包管理器**: uv（pip 可用但 uv 为主）
- **入口**: `service_mcp/server.py` — CLI 命令 `service-mcp`
- **工具数量**: 约 33 个（2 个示例实体 + CSV 导出示例）

## 快速命令

```bash
# 环境
uv venv && uv sync --dev

# 运行服务（任选一种传输）
uv run service-mcp stdio
uv run service-mcp streamable-http --host 0.0.0.0 --port 8001
uv run service-mcp sse --host 0.0.0.0 --port 8001
uv run service-mcp ui --dev-port 8080 --mcp-port 8001

# 测试（内存 SQLite，无需外部 DB；mysql/postgresql 参数化用例需对应服务运行）
pytest                          # 全部测试
pytest tests/test_config.py     # 单文件
pytest -k "test_name"           # 单测试

# Lint + 格式 + 类型
ruff check .
ruff check --fix .
ruff format .
mypy service_mcp

# 修改 filter/search 声明后重新生成 .pyi stub（跑两次，第二次应无 diff）
uv run python scripts/refresh_project_stub.py

# 生成演示数据
uv run python mock/mock_product_data.py

# 数据库迁移（幂等，可重复执行）
uv run python scripts/migrate_example.py
uv run python scripts/migrate_example.py --url sqlite+aiosqlite:///path/to/service_data.db

# 项目改名（模板 → 新项目；默认 dry-run 预览，加 --write 才落盘）
uv run python scripts/rename_project.py my_company --project my-company-mcp --display "My Company MCP"
uv run python scripts/rename_project.py my_company --project my-company-mcp --write
```

## 架构

```
service_mcp/
├── server.py          # FastMCP app + Typer CLI（stdio/sse/streamable-http/ui）
├── config.py          # MCPSettings 分层配置（env → TOML → code），前缀 MCP_，分隔符 __
├── apps/              # FastMCP Apps UI（config_app：数据库/缓存配置管理面板）
├── auth/              # JWT 认证 + 权限
│   ├── config.py      # AuthConfig（mode: tool/admin，从环境变量加载）
│   ├── context.py     # 请求上下文（current_owner / scope_visibility_where 三级可见性）
│   ├── decorator.py   # @mcp_perm(resource, action) 权限装饰器 + build_perm_code（码格式唯一来源）
│   ├── discovery.py   # get_entity_metadata / get_all_permissions（实体元数据缓存）
│   └── middleware.py  # JWTAuthMiddleware（admin 模式时启用，server.py 挂载）
├── db/core.py         # DBManager（异步 SQLAlchemy CRUD/分页）+ InfluxDBManager + 管理器缓存
├── error/exceptions.py # UniqueConflictError / ToolError（业务失败收口）等自定义异常
├── handlers/          # 业务逻辑层
│   ├── base_handlers.py   # CodeResolveMixin — FK code→id 解析、占位自动创建、写侧可见性收敛
│   ├── ownership.py   # 归属档位判据 + GOVERNANCE_RESOURCES（表名→资源码）治理注册表
│   ├── add_handlers.py    # 单条 + 批量插入（含价格冲突版本升级）
│   ├── delete_handlers.py # 注册表驱动的删除定位 + 孤儿标记
│   ├── update_handlers.py # 部分更新（None 字段跳过）
│   └── query_handlers.py  # 分页、外键显示展开、异常待办聚合
├── models/
│   ├── orm/           # Base（id/created_at/updated_at/created_by + EnumInt）+ Product/ProductPrice
│   │                  # + PARENT_ENTITY_MAP（父实体可见性注册表）
│   ├── pydantic/      # 动态 Filter/Search 生成器（builder.py）+ 实体请求/响应模型
│   └── schemas.py     # 数据库/缓存配置 + 分页（PaginationParams/PageData）
├── tools/             # MCP 工具定义
│   ├── __init__.py    # @global_tool 装饰器（配置类工具，Apps UI 可跨 App 调用）
│   ├── annotations.py # ToolAnnotations 预设（READ_ONLY / WRITE_* 四件套）
│   ├── crud_factory.py # 注册表驱动生成 add/update/delete 工具（单条+批量）
│   ├── crud_tools.py  # __all__ = register_crud_tools(globals()) —— 保持原样
│   ├── query_tools.py # 列表/搜索/枚举工具
│   ├── basic_tools.py # health、配置 CRUD、review_abnormal_items
│   ├── export_tools.py # CSV 导出示例工具（export_products_csv）
│   └── dict_tools.py  # dict_meta 实体元数据工具
├── task/              # 通用后台任务包（TaskManager 生命周期 + TaskScheduler cron 调度）
└── utils/             # enums（BaseEnum/Errcode/领域枚举）、log、path_utils、common、
                       # rate_limiter（按 key 限速）、spill（大结果溢出）、cron、export（CSV）
```

`fastmcp.json` — FastMCP 项目配置（source: `service_mcp/server.py`，transport: streamable-http:8001）。

工具自动发现机制：`server.py` 以 `FileSystemProvider(tools_dir)` 加载 `tools/` 包，
`crud_factory` 生成的工具注入 `crud_tools` 模块命名空间后自动成为 MCP 工具。
**注意：增删改工具没有独立的 `add_tools.py`/`update_tools.py`/`delete_tools.py`**
（由 `crud_factory.py` 动态生成）；`auth/middleware.py` 存在，admin 模式时由 `server.py` 挂载。

## 示例域契约（与 backend/frontend 对齐）

| 实体 | 字段 |
|---|---|
| Product | `code`（唯一业务编码）、`name`、`category`（1 实物商品 / 2 虚拟商品 / 3 服务）、`price`、`stock`、`is_active`、`remark`；MCP 教学列：`abnormal`、`is_deleted` |
| ProductPrice | 对外 `code`（= Product.code，FK 解析）、`price_date`、`price`；内部 `product_id`；教学列：`version`、`abnormal`；复合唯一键 `(product_id, price_date, version)` |

品类取值与文案以 backend `apps/demo_module/models.py` 的 `ProductCategoryChoices` 为准，
三处模板同源，改一边必须改另一边。

## 关键模式

### 工具注册
- 工具用 `@tool`（fastmcp.tools）；配置类工具额外用 `@global_tool`（`tools/__init__.py`，apps UI 可跨 App 调用）。
- 标签：`sys_tool`（健康检查）、`config_tool`（配置管理）、`domain_tool`（领域工具）。
- 权限：`@mcp_perm(resource, action)` → 权限码 `SM_01{resource}{action}`（resource 为两位资源码，action 为两位操作码）；
  码格式只在 `auth.decorator.build_perm_code` 一处（前缀常量 `PERM_PREFIX`），写侧判据要拼码也走它，别抄第二串字面量。
- 权限发现（`auth/discovery._TOOL_MODULES`）是手写清单：新工具模块**必须登记进去**，否则它声明的码不进
  `/permissions`、RBAC 里没有这一行（工具照旧能用、超管照旧能调，除超管一律 403）。
  这条不变量由 `tests/test_auth_discovery.py` 扫工具包把守。

### FK 解析（CodeResolveMixin）
业务编码（如 `code`）自动解析为内部 ID，调用方不暴露主键。注册表：
- `_CODE_RESOLVE_MAP`：code 字段 → (id 字段, 参照模型, 查询列)
- `_NAME_RESOLVE_MAP`：名称字段 → 按名称兜底解析（示例为空）
- `_OWN_CODE_FIELDS`：模型自身的唯一编码字段（不参与 FK 解析，参与唯一性校验）
- `_AUTO_CREATE_MODELS`：FK 解析失败时自动创建 `abnormal=Placeholder` 占位记录的模型

### 删除与孤儿标记
- `_DELETE_NAME_LOOKUP`：名称定位（同名报错列出候选项）
- `_COMPOUND_TARGET_REGISTRY`：复合键定位（如 `code + price_date`）
- `_ORPHAN_REGISTRY`：父模型 → [(子模型, 外键列)]，删除父记录时子记录标记 `abnormal=Orphaned`

### 动态 Filter/Search
`filter.py`/`search.py` 在导入时调用 `create_filter_class`/`create_search_class` 动态生成，
基于 ORM introspection，无需手写字段。`ProductFilter` 是显式 class（覆盖 keyword 跨字段搜索），
需在类定义后调用 `register_pyi_class(..., explicit=True)` 重新登记以便 stub 输出完整 class。
修改声明后运行 `scripts/refresh_project_stub.py` 重新生成 `.pyi`（stub 只 `ruff check --fix`，不 format）。

### 数据范围可见性与错误收口
- 模型带 `data_scope/owner_id` 列 → `scope_visibility_where()` 强制三级过滤
  （platform 全登录用户 / team 按 `ctx.team_ids` 命中 `team_id` 列 / personal 仅本人，
  superuser 也不可越）；带 `publish_status` 列时叠加发布门槛（PENDING/REJECTED 仅归属者，
  NULL 视为已审核）。
- 无归属列的子表 → 在 `models/orm.PARENT_ENTITY_MAP` 登记 `(父实体, 外键列)`，查询按
  "父实体可见"过滤，孤儿行（外键空/父不存在）豁免保持可见。
- **写侧与读侧同一条谓词**：单条更新/删除经 `CodeResolveMixin._resolve_record_id`、批量更新经
  `_visible_ids` 收敛到可见子集。**越权与"记录不存在"必须回同一句话**（`RECORD_NOT_FOUND` +
  "不存在，或不在你的数据范围内"），批量提示也不区分两者——两种答案并存就是一条探测信道，
  而回"不可见"同样是泄露（`tests/test_write_scope.py` 把"两句归一后逐字相等"钉成断言）。
  **缺身份时按模式分叉**（`ownership.require_identity_for_scoped_write`，唯一口径
  `auth.config.is_admin_mode`）：tool 模式不收敛（与读侧"无鉴权即全量"同口径，采集/后台照常），
  admin 模式一律拒绝——装饰器的 fail-closed 只挡工具调用，直接调 handler 绕得开它。
  已知缺口（与上游同）：无归属列的子表只在读侧叠加父实体可见性，写侧不叠加，
  他人子表行仍写得进去，补齐它是独立改动。
- **新增的档位落点由 `handlers/ownership.assert_add_allowed` 判**（在归属注入之后，判的是将要落库的
  真值）：档位值只认 `DataScope` 词表（列是裸字符串无 CHECK、读侧只认字面量，不认识的值写进去就
  "谁都读不到"）、`platform` 需该实体的治理码、`personal` 的 `owner_id` 只能是自己、`team` 的
  `team_id` 只能在 `ctx.team_ids` 里。治理码按表名登记在 `ownership.GOVERNANCE_RESOURCES`
  （值是**资源码**，完整码经 `build_perm_code` 现拼），登记的码随 `/permissions` 下发才谈得上授予；
  **未登记的实体平台档只剩超管写得**——示例域不带归属列故整条不触发，下游补了 `data_scope` 列就要决定
  是否登记。无鉴权上下文照旧不校验（同读侧口径，但别把它当安全边界）。
- **审核/治理类工具不要复用整行可见性**：审核者按定义读不到提交人的 PENDING/personal 行，
  套用这条谓词会让审核流程静默失灵。这类动作的边界应落在**它自己的权限码**上
  （本仓已落 `AuthAction.Govern="09"`，普通更新码不含治理），别把两个守卫"统一"掉。
- 带 `is_deleted` 列的模型列表/搜索默认隐藏软删行（查询层自动叠加）。
- 业务可预期失败在 handler 内 `raise ToolError(msg, Errcode.X)`（ValueError 子类），
  crud_factory 收口为 UtilResponse，绝不 500 化；批量工具受 `MAX_BATCH_SIZE=200` 上限保护。
- 工具注解用 `tools/annotations.py` 预设（READ_ONLY/WRITE_IDEMPOTENT/WRITE_MUTATING/
  WRITE_DESTRUCTIVE），新增工具按语义挂 `annotations=`。

### 配置系统
分层：显式参数 → 环境变量 → TOML 文件。环境前缀 `MCP_`，嵌套分隔符 `__`。
TOML 路径由 `MCP_ENV` 决定 → `configs/config.{env}.toml`（git 忽略，首次启动自动生成）。
无配置时默认 SQLite 内存 + Redis。

### 日志输出与迁移脚本
- 控制台日志按 `sys.stdout.isatty()` 分档：交互终端用 rich，重定向到文件/管道时改一行一条纯文本
  （rich 的折行与边框会让日志没法 grep）。`configure_logging` 只清 root 的处理器，管不到 FastMCP
  自己那个 logger，故 `server.py` 启动时对 `"fastmcp"` 补调一次 `utils/log.demote_console_rendering()`。
- 迁移脚本共享 `scripts/_migration_common.py`（新增脚本从这里 import，别复制实现）；
  打印连接串一律 `masked_url(url)`——只遮口令，方言/用户/主机/库名保留；
  `tests/test_migrate_url_masking.py` 会把 `scripts/*.py` 里裸着打 `{url}` 的 print 判红
  （预演是只读动作，输出最容易被截图转发）。

### 测试约定
- 全部测试用内存 SQLite（`sqlite+aiosqlite:///:memory:`）；默认无需外部服务
- `asyncio_mode = "auto"`，无需 `@pytest.mark.asyncio`
- conftest fixtures：`handler_db`（注册到管理器缓存的 DBManager）、`seeded_product`/`seeded_price`、
  autouse 的 `clean_globals`/`clean_manager_cache`/`patch_toml_file`
- `db_manager` fixture 参数化 sqlite/sqlite_file/mysql/postgresql（后两者需服务运行）
- 测试模式：调用 handler.handle() → 断言 UtilResponse.code → session 查询验证入库结果
- `pytest -k "test_name"` 可运行单个测试；`pytest tests/test_config.py` 可运行单文件

## 环境文件

| 文件 | 用途 |
|------|------|
| `.env` | 系统级（MCP_ENV、MCP_TRANSPORT），git 忽略 |
| `.env.local` | 环境特定覆盖（git 忽略，存在才加载） |
| `.env.dev` / `.env.prod` / `.env.test` | 模板示例 |
| `.env.example` | 最小示例 |

## Docker

```bash
# 一键部署（生产）
cp docker/.env.example docker/.env
./docker/ctl.sh deploy -e prod

# 仅基础设施（应用本地运行）
cd docker && docker compose up -d
```

服务：PostgreSQL 18（5432）、Redis 8（6379）、可选 pgAdmin（5050）。

## 新增实体清单

1. ORM 模型（继承 `Base`，唯一业务码带 `comment`，加 `abnormal` 列；需多用户隔离的加
   `data_scope/owner_id`（可选 `team_id/publish_status`）列）→ `models/orm/__init__.py` 导出；
   无归属列的子表在 `PARENT_ENTITY_MAP` 登记父实体与外键列
2. Pydantic `<Entity>Base/Create/Update/Delete/Response`（Delete 继承 `BaseDeleteModel`）
3. `filter.py` / `search.py` 声明 + `refresh_project_stub.py` 重新生成 stub
4. handler 注册表：`_CODE_RESOLVE_MAP`、`_NAME_RESOLVE_MAP`、`_OWN_CODE_FIELDS`、
   `_AUTO_CREATE_MODELS`、`_DELETE_NAME_LOOKUP`、`_COMPOUND_TARGET_REGISTRY`、
   `_ORPHAN_REGISTRY`、`FIELD_MAPPING_CONFIG`
5. `crud_factory._ENTITIES` 一行 + `query_tools.py` 列表/搜索工具
6. `utils/enums.py`：`EntityType` / `AuthResource` / 领域枚举
7. `auth/discovery.py`：`get_entity_metadata` 模型表；**新工具模块要加进 `_TOOL_MODULES`**
   （漏登记 = 它的码不进 `/permissions`）；带 `data_scope` 列且要把平台档下放给非超管的实体，
   在 `handlers/ownership.GOVERNANCE_RESOURCES` 按表名登记资源码
8. mock `TABLE_META` + tests seeded fixtures

## 风格说明

- Ruff 配置：line-length 100、target py312、quote-style double
- 大量 lint 规则被有意忽略（见 `[tool.ruff.lint] ignore`），不要未经确认重新启用
- 中文注释/docstring 是项目惯例
- `RUF001`/`RUF002`/`RUF003`（歧义 Unicode）已忽略 —— 中文全角标点是有意为之
- `TC001`/`TC002`/`TC003`（move imports to TYPE_CHECKING）已忽略 —— pydantic 运行时需要这些导入
- mypy 配置：`ignore_missing_imports = true`、`follow_imports = "skip"`、多模块 override 见 pyproject.toml
- **禁止用 PowerShell 批量替换文件**（毁中文编码），批量改动用文件工具逐文件处理
- 代码注释与提交信息不得出现版本号与阶段标识
