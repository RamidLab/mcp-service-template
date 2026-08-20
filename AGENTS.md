# AGENTS.md — Service MCP 模板

## 项目概览

通用 MCP 服务模板（FastMCP + SQLAlchemy async + Pydantic v2 + Typer CLI），含示例实体
Product / ProductPrice，演示完整 CRUD + 外键解析 + 动态 Filter/Search 链路。

- **Python**: 3.12+ 必须
- **包管理器**: uv（pip 可用但 uv 为主）
- **入口**: `service_mcp/server.py` — CLI 命令 `service-mcp`
- **工具数量**: 约 30 个（2 个示例实体）

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

# 项目改名（模板 → 新项目）
uv run python scripts/rename_project.py my_company --project my-company-mcp --display "My Company MCP"
```

## 架构

```
service_mcp/
├── server.py          # FastMCP app + Typer CLI（stdio/sse/streamable-http/ui）
├── config.py          # MCPSettings 分层配置（env → TOML → code），前缀 MCP_，分隔符 __
├── apps/              # FastMCP Apps UI（config_app：数据库/缓存配置管理面板）
├── auth/              # JWT 认证 + 权限
│   ├── config.py      # AuthConfig（mode: tool/admin，从环境变量加载）
│   ├── context.py     # 请求上下文（current_owner / visible_owners）
│   ├── decorator.py   # @mcp_perm(resource, action) 权限装饰器
│   ├── discovery.py   # get_entity_metadata / get_all_permissions（实体元数据缓存）
│   └── middleware.py  # JWTAuthMiddleware（admin 模式时启用）
├── db/core.py         # DBManager（异步 SQLAlchemy CRUD/分页）+ InfluxDBManager + 管理器缓存
├── error/exceptions.py # UniqueConflictError 等自定义异常
├── handlers/          # 业务逻辑层
│   ├── base_handlers.py   # CodeResolveMixin — FK code→id 解析、占位自动创建
│   ├── add_handlers.py    # 单条 + 批量插入（含价格冲突版本升级）
│   ├── delete_handlers.py # 注册表驱动的删除定位 + 孤儿标记
│   ├── update_handlers.py # 部分更新（None 字段跳过）
│   └── query_handlers.py  # 分页、外键显示展开、异常待办聚合
├── models/
│   ├── orm/           # Base（id/created_at/updated_at/created_by + EnumInt）+ Product/ProductPrice
│   ├── pydantic/      # 动态 Filter/Search 生成器（builder.py）+ 实体请求/响应模型
│   └── schemas.py     # 数据库/缓存配置 + 分页（PaginationParams/PageData）
├── tools/             # MCP 工具定义
│   ├── __init__.py    # @global_tool 装饰器（配置类工具，Apps UI 可跨 App 调用）
│   ├── crud_factory.py # 注册表驱动生成 add/update/delete 工具（单条+批量）
│   ├── crud_tools.py  # __all__ = register_crud_tools(globals()) —— 保持原样
│   ├── query_tools.py # 列表/搜索/枚举工具
│   ├── basic_tools.py # health、配置 CRUD、review_abnormal_items
│   └── dict_tools.py  # dict_meta 实体元数据工具
└── utils/             # enums（BaseEnum/Errcode/领域枚举）、log、path_utils、common
```

`fastmcp.json` — FastMCP 项目配置（source: `service_mcp/server.py`，transport: streamable-http:8001）。

工具自动发现机制：`server.py` 以 `FileSystemProvider(tools_dir)` 加载 `tools/` 包，
`crud_factory` 生成的工具注入 `crud_tools` 模块命名空间后自动成为 MCP 工具。
**注意：本模板没有 `middleware.py`，也没有 `add_tools.py`/`update_tools.py`/`delete_tools.py`**
（增删改工具由 `crud_factory.py` 动态生成）。

## 关键模式

### 工具注册
- 工具用 `@tool`（fastmcp.tools）；配置类工具额外用 `@global_tool`（`tools/__init__.py`，apps UI 可跨 App 调用）。
- 标签：`sys_tool`（健康检查）、`config_tool`（配置管理）、`domain_tool`（领域工具）。
- 权限：`@mcp_perm(resource, action)` → 权限码 `SM_01{resource}{action}`（resource 为两位资源码，action 为两位操作码）。

### FK 解析（CodeResolveMixin）
业务编码（如 `product_code`）自动解析为内部 ID，调用方不暴露主键。注册表：
- `_CODE_RESOLVE_MAP`：code 字段 → (id 字段, 参照模型, 查询列)
- `_NAME_RESOLVE_MAP`：名称字段 → 按名称兜底解析（示例为空）
- `_OWN_CODE_FIELDS`：模型自身的唯一编码字段（不参与 FK 解析，参与唯一性校验）
- `_AUTO_CREATE_MODELS`：FK 解析失败时自动创建 `abnormal=Placeholder` 占位记录的模型

### 删除与孤儿标记
- `_DELETE_NAME_LOOKUP`：名称定位（同名报错列出候选项）
- `_COMPOUND_TARGET_REGISTRY`：复合键定位（如 `product_code + price_date`）
- `_ORPHAN_REGISTRY`：父模型 → [(子模型, 外键列)]，删除父记录时子记录标记 `abnormal=Orphaned`

### 动态 Filter/Search
`filter.py`/`search.py` 在导入时调用 `create_filter_class`/`create_search_class` 动态生成，
基于 ORM introspection，无需手写字段。`ProductFilter` 是显式 class（覆盖 keyword 跨字段搜索），
需在类定义后调用 `register_pyi_class(..., explicit=True)` 重新登记以便 stub 输出完整 class。
修改声明后运行 `scripts/refresh_project_stub.py` 重新生成 `.pyi`（stub 只 `ruff check --fix`，不 format）。

### 配置系统
分层：显式参数 → 环境变量 → TOML 文件。环境前缀 `MCP_`，嵌套分隔符 `__`。
TOML 路径由 `MCP_ENV` 决定 → `configs/config.{env}.toml`（git 忽略，首次启动自动生成）。
无配置时默认 SQLite 内存 + Redis。

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

1. ORM 模型（继承 `Base`，唯一业务码带 `comment`，加 `abnormal` 列）→ `models/orm/__init__.py` 导出
2. Pydantic `<Entity>Base/Create/Update/Delete/Response`（Delete 继承 `BaseDeleteModel`）
3. `filter.py` / `search.py` 声明 + `refresh_project_stub.py` 重新生成 stub
4. handler 注册表：`_CODE_RESOLVE_MAP`、`_NAME_RESOLVE_MAP`、`_OWN_CODE_FIELDS`、
   `_AUTO_CREATE_MODELS`、`_DELETE_NAME_LOOKUP`、`_COMPOUND_TARGET_REGISTRY`、
   `_ORPHAN_REGISTRY`、`FIELD_MAPPING_CONFIG`
5. `crud_factory._ENTITIES` 一行 + `query_tools.py` 列表/搜索工具
6. `utils/enums.py`：`EntityType` / `AuthResource` / 领域枚举
7. `auth/discovery.py`：`get_entity_metadata` 模型表
8. mock `TABLE_META` + tests seeded fixtures

## 风格说明

- Ruff 配置：line-length 100、target py312、quote-style double
- 大量 lint 规则被有意忽略（见 `[tool.ruff.lint] ignore`），不要未经确认重新启用
- 中文注释/docstring 是项目惯例
- `RUF001`/`RUF002`/`RUF003`（歧义 Unicode）已忽略 —— 中文全角标点是有意为之
- `TC001`/`TC002`/`TC003`（move imports to TYPE_CHECKING）已忽略 —— pydantic 运行时需要这些导入
- mypy 配置：`ignore_missing_imports = true`、`follow_imports = "skip"`、多模块 override 见 pyproject.toml
