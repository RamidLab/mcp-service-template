# Service MCP — 通用 FastMCP + SQLAlchemy CRUD 模板

一个开箱即用的通用 [FastMCP](https://github.com/jlowin/fastmcp) 服务模板，内置 SQLAlchemy 异步
CRUD 全套能力。由真实的基金净值 MCP 服务蒸馏而来，用于快速搭建新的 MCP 数据管理服务。

**技术栈**：Python 3.12+ · FastMCP 3.x · SQLAlchemy 2.x（async）· Pydantic v2 · Typer CLI · uv

---

## 特性

- **注册表驱动的 CRUD 工具** —— 新增/更新/删除（单条 + 批量）由一行实体注册表自动生成，无逐实体样板代码。
- **外键 code 自动解析** —— 业务编码（`product_code`）由处理器层自动解析为内部 ID，调用方不感知主键。
- **占位记录自动创建** —— 子记录引用不存在的父记录时，自动创建 `abnormal=Placeholder` 的占位父记录
  （例如：为未知产品添加价格记录时自动建占位产品）。
- **孤儿标记** —— 删除父记录时，将子记录标记为 `abnormal=Orphaned` 而非级联删除；
  `review_abnormal_items` 工具聚合所有待人工审核的记录。
- **复合键删除** —— 子记录可按业务复合键定位（`product_code + price_date`）。
- **动态 Filter/Search** —— 过滤/搜索类在导入时由 ORM 内省自动生成；`.pyi` stub 由脚本重新生成，IDE 友好。
- **冲突版本化** —— 同日同源价格冲突自动升级 `version` 列并标记待审核。
- **多传输 CLI** —— `stdio` / `sse` / `streamable-http` / `ui`（FastMCP Apps 控制台）。
- **分层配置** —— 环境变量 → TOML → 代码默认值（`MCP_` 前缀，`MCP_ENV` 选择 TOML）。
- **认证就绪** —— JWT 中间件 + `mcp_perm` 权限装饰器 + 权限自动发现。
- **Docker 部署** —— compose 栈（PostgreSQL 18 + Redis 8，可选 pgAdmin）+ 生命周期脚本（`ctl.sh` / `ctl.ps1`）。
- **配套工具** —— 演示数据生成器、幂等迁移示例、SQLite/MySQL/PostgreSQL/InfluxDB 支持、配置管理 UI。

## 快速开始

```bash
uv venv && uv sync --dev

# 运行服务（任选一种传输）
uv run service-mcp stdio
uv run service-mcp streamable-http --host 0.0.0.0 --port 8001
uv run service-mcp sse --host 0.0.0.0 --port 8001
uv run service-mcp ui --dev-port 8080 --mcp-port 8001
```

首次启动自动生成 `configs/config.{MCP_ENV}.toml`（默认 SQLite 内存 + Redis 缓存配置），零配置即可运行。

## 示例实体

模板内置一个最小领域 —— **Product（产品）+ ProductPrice（产品价格）**，端到端实现了你为自己的
实体需要复刻的全部模式：

| 实体 | 演示的模式 |
|---|---|
| `Product` | 唯一业务编码、软删除标记、占位自动创建（孤儿**父**表） |
| `ProductPrice` | 外键 code 解析、复合唯一键（`product_id + price_date + data_source + version`）、版本冲突检测、孤儿标记目标、复合键删除 |

链路示例：`add_product` → `AddHandler` → `CodeResolveMixin._resolve_fk_codes` → 价格记录自动把
`product_code` 解析为 `product_id`；`delete_product` 将其所有价格标记 `abnormal=Orphaned`；
`add_product_price` 若与同日同源已有价格冲突，自动 `version+1` 并标记 `abnormal=PriceConflict`。

## 项目结构

```
service_mcp/
├── server.py          # FastMCP app + Typer CLI（stdio/sse/streamable-http/ui）
├── config.py          # MCPSettings 分层配置（env → TOML → code）
├── apps/              # FastMCP Apps UI（config_app：数据库/缓存配置管理面板）
├── auth/              # JWT 中间件、mcp_perm 权限装饰器、权限/实体发现
├── db/                # DBManager（异步 SQLAlchemy CRUD/分页）+ InfluxDBManager
├── handlers/          # CodeResolveMixin + Add/Update/Delete/Query 处理器
├── models/
│   ├── orm/           # SQLAlchemy 模型（base.py 审计列、product.py 示例实体）
│   ├── pydantic/      # 动态 Filter/Search 生成器 + 各实体请求/响应模型
│   └── schemas.py     # 数据库/缓存配置 schema + 分页
├── tools/             # crud_factory（注册表驱动）、query_tools、basic_tools、dict_tools
└── utils/             # 枚举、日志、路径工具
configs/               # config.example.toml 骨架（各环境 TOML 被 git 忽略）
docker/                # compose 文件、entrypoint、ctl.sh/ctl.ps1
mock/                  # mock_product_data.py
scripts/               # rename_project.py、refresh_project_stub.py、migrate_example.py
tests/                 # pytest 测试套件（内存 SQLite）
```

## 新增实体

1. **ORM**：在 `service_mcp/models/orm/<entity>.py` 创建继承 `Base` 的模型（自动获得审计列）；
   唯一业务编码列务必带 `comment`（用于友好重复提示），并加 `abnormal: AbnormalType | None` 列用于孤儿标记。
   在 `models/orm/__init__.py` 导出（注意 `base` 先导入）。
2. **Pydantic**：在 `models/pydantic/<entity>.py` 编写 `<Entity>Base` / `Create` / `Update` /
   `Delete`（继承 `BaseDeleteModel`，至少一个定位字段）/ `Response`；参考 `product_validators.py` 复用校验帮手。
3. **Filter/Search**：在 `models/pydantic/filter.py` / `search.py` 添加 `create_filter_class(...)` /
   `create_search_class(...)` 调用。若用显式 `class` 覆盖生成的类，需再调
   `register_pyi_class(..., explicit=True)` 重新登记。
4. **重新生成 stub**：`uv run python scripts/refresh_project_stub.py`（跑两次，第二次应无 diff）。
5. **Handlers**：在以下注册表添加行 —— `_CODE_RESOLVE_MAP`（外键 code）、`_NAME_RESOLVE_MAP`
   （名称兜底）、`_OWN_CODE_FIELDS`（自有唯一码）、`_AUTO_CREATE_MODELS`（占位自动创建）、
   `_DELETE_NAME_LOOKUP`、`_COMPOUND_TARGET_REGISTRY`（复合删除键）、`_ORPHAN_REGISTRY`
   （删除时标记的子表）、`FIELD_MAPPING_CONFIG`（查询结果的外键显示字段）。
6. **工具**：在 `crud_factory._ENTITIES` 添加一行（自动获得单条/批量增删改工具），
   在 `query_tools.py` 添加列表/搜索工具。
7. **枚举**：在 `utils/enums.py` 添加 `EntityType` / `AuthResource` 条目及领域枚举。
8. **Mock/测试**：在 `mock/mock_product_data.py` 的 `TABLE_META` 添加一行；
   在 `tests/conftest.py` 添加 seeded fixtures。

## 项目改名（一条命令）

模板使用占位符命名（`service_mcp` / `service-mcp` / "Service MCP"）。基于模板创建新项目：

```bash
uv run python scripts/rename_project.py my_company \
    --project my-company-mcp --display "My Company MCP" --db my_company_data
uv sync            # 重新生成 uv.lock / 安装依赖
uv run pytest      # 确认测试通过
```

脚本会替换所有文件内容并重命名包目录。先加 `--dry-run` 预览。
`uv.lock` 不参与替换 —— 用 `uv sync` 重新生成。

## Docker 部署

```bash
cp docker/.env.example docker/.env   # 修改密码/数据库名
./docker/ctl.sh deploy -e prod       # Windows 使用 ctl.ps1
```

仅基础设施（应用本地运行）：

```bash
cd docker && docker compose up -d
```

服务：PostgreSQL 18（5432）、Redis 8（6379）、可选 pgAdmin（5050）。

## 配置参考

| 环境变量 | 含义 | 默认值 |
|---|---|---|
| `MCP_ENV` | 环境名；选择 `configs/config.{env}.toml` | `dev` |
| `MCP_CONFIG_PRIORITY` | `init_first` / `env_first` / `toml_first` / `env_only` / `toml_only` | `init_first` |
| `MCP_TRANSPORT` | 默认传输方式 | `stdio` |
| `MCP_HOST` / `MCP_PORT` / `MCP_UI_PORT` | HTTP 传输绑定 | `0.0.0.0` / `8001` / `8080` |
| `MCP_CACHE_ENABLED` | 启用 Redis 缓存 | `true` |
| `MCP_AUTH_MODE` | `tool` 或 `admin`（JWT） | `tool` |
| `MCP_DATABASES__<NAME>__*` | 各数据库配置（`__` 嵌套） | — |
| `MCP_LOGGING__*` | 日志配置（控制台/文件/JSON 轮转） | — |

## 测试与质量

```bash
pytest                          # 全部测试（内存 SQLite，无需外部服务）
ruff check .                    # 代码检查
ruff format .                   # 代码格式化
mypy service_mcp                # 类型检查
```

## License

MIT
