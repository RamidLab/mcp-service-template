__all__ = ["cond", "config_app", "config_app_ui", "switch_default_config", "test_connection"]

from collections import Counter
from typing import Any

from fastmcp import FastMCPApp
from prefab_ui.actions import CloseOverlay, SetState, ShowToast
from prefab_ui.app import PrefabApp
from prefab_ui.rx import ERROR, EVENT, RESULT, Rx
from pydantic import SecretStr

from service_mcp.apps import CallTool
from service_mcp.apps.prefab_compat import (
    H1,
    H2,
    Alert,
    AlertDescription,
    AlertTitle,
    Badge,
    Button,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Column,
    Container,
    Dashboard,
    DashboardItem,
    DataTable,
    DataTableColumn,
    Dialog,
    Div,
    Form,
    If,
    Input,
    Label,
    Loader,
    Muted,
    Popover,
    Row,
    Select,
    SelectOption,
    Text,
)
from service_mcp.config import get_settings
from service_mcp.models.common import UtilResponse
from service_mcp.models.schemas import CacheConfig, DatabaseConfig
from service_mcp.utils.enums import NodeStatus
from service_mcp.utils.log import get_logger


config_app = FastMCPApp("Config Tools")

logger = get_logger(__name__)


def cond(pairs: list[tuple[Rx, Any]], default: Any = None) -> Any:
    """
    构建 Rx 三元表达式链，根据条件返回对应的值

    Args:
        pairs:  条件值对列表，每个元素为 (condition, value)
        default:  如果所有条件都不匹配的默认值

    Returns:
        匹配结果
    """
    expr = default
    for _cond, val in reversed(pairs):
        expr = _cond.then(val, expr)
    return expr


@config_app.tool(name="get_render_info", description="获取渲染信息")
def get_render_info() -> dict[str, Any]:
    """
    获取渲染信息，包括数据库和缓存的状态汇总及详细列表。
    """
    settings = get_settings()

    def prepare_config_list(
        configs: dict[str, DatabaseConfig | CacheConfig], name_key: str
    ) -> tuple[list[dict[str, Any]], Counter[NodeStatus]]:
        """
        处理数据库或缓存的配置列表，返回数据列表和状态计数器

        Args:
            configs: 配置字典，键为配置名称，值为配置对象
            name_key: 配置名称键名，默认 "db_name" 或 "cache_name"

        Returns:
            数据列表和状态计数器
        """
        data = []
        statuses = []
        for name, cfg in configs.items():
            item = {
                **cfg.model_dump(),
                name_key: name,
                "status_component": cfg.status.component,
            }
            if item.get("db_password"):
                db_password = item["db_password"]
                item["db_password"] = (
                    db_password.get_secret_value()
                    if isinstance(db_password, SecretStr)
                    else db_password
                )
            if item.get("cache_pass"):
                cache_pass = item["cache_pass"]
                item["cache_pass"] = (
                    cache_pass.get_secret_value()
                    if isinstance(cache_pass, SecretStr)
                    else cache_pass
                )
            if item.get("influxdb_token"):
                token = item["influxdb_token"]
                item["influxdb_token"] = (
                    token.get_secret_value() if isinstance(token, SecretStr) else token
                )
            data.append(item)
            statuses.append(item.get("status"))
        return data, Counter(statuses)

    def _calc_counts(statuses: Counter[NodeStatus], prefix: str) -> dict[str, Any]:
        """
        根据状态列表计算各类计数，并以 prefix 作为键前缀

        Args:
            statuses: 状态计数器
            prefix: 键前缀

        Returns:
            包含各类计数的字典
        """
        counter = Counter(statuses)
        online = counter.get(NodeStatus.Active, 0)
        offline = counter.get(NodeStatus.Inactive, 0)
        deactivate = counter.get(NodeStatus.Deactivate, 0)
        error = counter.get(NodeStatus.Error, 0)
        unknown = counter.get(NodeStatus.Unknown, 0)
        total = counter.total() - deactivate - error - unknown
        return {
            f"{prefix}_online_count": online,
            f"{prefix}_offline_count": offline,
            f"{prefix}_deactivate_count": deactivate,
            f"{prefix}_error_count": error,
            f"{prefix}_unknown_count": unknown,
            f"{prefix}_total_count": total,
        }

    # 处理数据库
    db_data, db_statuses = prepare_config_list(settings.databases, "db_name")
    # 处理缓存
    cache_data, cache_statuses = prepare_config_list(settings.caches, "cache_name")

    return {
        "db_list": db_data,
        **_calc_counts(db_statuses, "db"),
        "cache_list": cache_data,
        **_calc_counts(cache_statuses, "cache"),
    }


@config_app.tool(name="switch_default_config", description="切换默认配置")
def switch_default_config(_class: str, _type: str, config: dict[str, Any]) -> dict[str, Any]:
    """
    切换默认配置

    Args:
        _class: 配置类型，"db" 或 "cache"
        _type: 配置类型，"sqlite", "mysql", "postgresql", "influxdb" 或 "redis"
        config: 配置字典

    Returns:
        默认配置
    """
    # 数据库默认配置映射 (host, port, db_main, org, bucket)
    db_defaults = {
        "sqlite": ("memory", 0, "", "", ""),
        "mysql": ("127.0.0.1", 3306, "service_data", "", ""),
        "postgresql": ("127.0.0.1", 5432, "service_data", "", ""),
        "influxdb": ("127.0.0.1", 8086, "", "service_data", "service_data"),
    }
    # 缓存默认配置映射 (host, port)
    cache_defaults = {
        "redis": ("127.0.0.1", 6379),
    }

    if _class == "db":
        host, port, def_db, org, bucket = db_defaults.get(_type, ("", 0, "", "", ""))
        return {
            **config,
            "db_host": host,
            "db_port": port,
            "db_username": "",
            "db_password": "",
            "db_main": def_db,
            "influxdb_token": "",
            "influxdb_org": org,
            "influxdb_bucket": bucket,
            "status": NodeStatus.Unknown,
        }
    if _class == "cache":
        host, port = cache_defaults.get(_type, ("", 0))
        return {
            **config,
            "cache_host": host,
            "cache_port": port,
            "cache_pass": "",
            "status": NodeStatus.Unknown,
        }
    return {}


@config_app.tool(name="test_connection", description="测试连接")
def test_connection(
    _class: str, config: dict[str, Any]
) -> UtilResponse[DatabaseConfig | CacheConfig]:
    """
    测试连接

    Args:
        _class: 配置类型，"db" 或 "cache"
        config: 配置字典

    Returns:
        连接结果
    """
    settings = get_settings()
    if _class == "db":
        _config = DatabaseConfig.model_validate(config)
    elif _class == "cache":
        _config = CacheConfig.model_validate(config)
    else:
        logger.error(f"无效的配置类型: {_class}")
        raise ValueError(f"Invalid class type: {_class}")
    result = settings.test_connection(_config)
    return result


def loder_overlay() -> None:
    """显示加载中弹窗"""
    with If(Rx("dialog_loading")):
        with Container(css_class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"):
            Loader(size="lg")


def status_display(prefix: str, action: str) -> None:
    """
    显示连接状态

    Args:
        prefix: 配置前缀，"db" 或 "cache"
        action: 操作类型，"add" 或 "update"
    """
    with If(Rx(f"{prefix}_action_result") != ""):
        with If(Rx(f"{prefix}_{action}_args.status") == NodeStatus.Active):
            with Alert(variant="success", icon="circle-check"):
                AlertTitle("连接成功")
        with If(Rx(f"{prefix}_{action}_args.status") == NodeStatus.Inactive):
            with Alert(icon="circle-alert"):
                AlertTitle("连接失败")
                AlertDescription(str(Rx(f"{prefix}_action_result")))
        with If(Rx(f"{prefix}_{action}_args.status") == NodeStatus.AuthFailed):
            with Alert(icon="circle-alert"):
                AlertTitle("认证失败")
                AlertDescription(str(Rx(f"{prefix}_action_result")))
        with If(Rx(f"{prefix}_{action}_args.status") == NodeStatus.Error):
            with Alert(variant="destructive", icon="circle-x"):
                AlertTitle("错误信息")
                AlertDescription(str(Rx(f"{prefix}_action_result")))


def button_test(prefix: str, action: str) -> None:
    """
    显示测试按钮

    Args:
        prefix: 配置前缀，"db" 或 "cache"
        action: 操作类型，"add" 或 "update"
    """
    (
        Button(
            "测试",
            variant="outline",
            button_type="button",
            on_click=[
                SetState("dialog_loading", True),
                CallTool(
                    "test_connection",
                    arguments={"_class": prefix, "config": Rx(f"{prefix}_{action}_args")},
                    on_success=[
                        SetState(f"{prefix}_action_result", RESULT.message),
                        SetState(f"{prefix}_{action}_args.status", RESULT.data.status),
                        SetState("dialog_loading", False),
                    ],
                    on_error=[
                        SetState(f"{prefix}_action_result", ERROR),
                        SetState(f"{prefix}_{action}_args.status", NodeStatus.Error),
                        ShowToast(
                            f"{'数据库' if prefix == 'db' else '缓存'}连接失败", variant="error"
                        ),
                        SetState("dialog_loading", False),
                    ],
                ),
            ],
        ),
    )


def get_status_component_args(prefix: str, action: str) -> tuple[str, str]:
    """
    获取连接状态组件的参数
    Args:
        prefix: 配置前缀，"db" 或 "cache"
        action: 操作类型，"add" 或 "update"

    Returns:
        连接状态和状态标签
    """
    _status_pairs = [
        (Rx(f"{prefix}_{action}_args.status") == member.value, member) for member in NodeStatus
    ]
    status = cond(_status_pairs, default=NodeStatus.Unknown)
    status_variant = cond(
        [(cond_expr, member.label) for cond_expr, member in _status_pairs],
        default=NodeStatus.Unknown.label,
    )
    return status, status_variant


@config_app.ui(name="config_app", title="配置工具应用", description="配置工具应用")
def config_app_ui() -> PrefabApp:
    """
    配置工具应用

    Returns:
        PrefabApp 应用实例
    """
    with Dashboard(columns=12, row_height="auto", gap=4) as dashboard:
        with Dialog(
            title="添加数据库", name="add_db_dialog", css_class="fixed inset-0 bg-black/50"
        ):
            Div()
            with Form():
                loder_overlay()
                with Column(gap=2):
                    Label("数据库类型")
                    with Select(
                        placeholder="选择数据库类型...",
                        name="db_add_args.db_type",
                        on_change=[
                            SetState("db_add_args.db_type", EVENT),
                            SetState("db_action_result", ""),
                            CallTool(
                                "switch_default_config",
                                arguments={
                                    "_class": "db",
                                    "_type": Rx("db_add_args.db_type"),
                                    "config": Rx("db_add_args"),
                                },
                                on_success=[SetState("db_add_args", RESULT)],
                            ),
                        ],
                    ):
                        SelectOption(value="sqlite", label="SQLite", selected=True)
                        SelectOption(value="mysql", label="Mysql")
                        SelectOption(value="postgresql", label="Postgresql")
                        SelectOption(value="influxdb", label="InfluxDB")
                with Column(gap=2):
                    Label("数据库名称")
                    Input(
                        name="db_add_args.db_name", placeholder="如：mysql-default", required=True
                    )
                with Row(gap=2):
                    with Column(gap=2):
                        Label("数据库地址")
                        Input(
                            name="db_add_args.db_host",
                            placeholder="如：127.0.0.1",
                            required=True,
                        )
                    with If(Rx("db_add_args.db_type") != "sqlite"):
                        with Column(gap=2):
                            Label("数据库端口")
                            Input(
                                name="db_add_args.db_port",
                                placeholder="如：3306",
                                input_type="number",
                            )
                        with If(Rx("db_add_args.db_type") != "influxdb"):
                            with Column(gap=2):
                                Label("数据库用户名")
                                Input(name="db_add_args.db_username", placeholder="如：root")
                            with Column(gap=2):
                                Label("数据库密码")
                                Input(
                                    name="db_add_args.db_password",
                                    placeholder="如：123456",
                                    input_type="password",
                                )
                with If(Rx("db_add_args.db_type") != "sqlite"):
                    with Column(gap=2):
                        Label("默认数据库")
                    Input(name="db_add_args.db_main", placeholder="如：service_data")
                with If(Rx("db_add_args.db_type") == "influxdb"):
                    with Row(gap=2):
                        with Column(gap=2):
                            Label("InfluxDB 令牌")
                            Input(
                                name="db_add_args.influxdb_token",
                                placeholder="如：token-123abc...",
                                input_type="password",
                            )
                        with Column(gap=2):
                            Label("InfluxDB 组织")
                            Input(name="db_add_args.influxdb_org", placeholder="如：service_data")
                        with Column(gap=2):
                            Label("InfluxDB 桶")
                            Input(
                                name="db_add_args.influxdb_bucket", placeholder="如：service_data"
                            )
                with Column(gap=2):
                    Label("连接池大小")
                    Input(name="db_add_args.db_pool_size", placeholder="如：5", input_type="number")
                with Column(gap=2):
                    Label("SQL 打印")
                    with Select(
                        name="db_add_args.db_sql_echo", placeholder="选择是否打印 SQL 语句"
                    ):
                        SelectOption(value="open", label="是")
                        SelectOption(value="close", label="否", selected=True)
                with Column(gap=2):
                    status, status_variant = get_status_component_args(prefix="db", action="add")

                    with Row(gap=2, css_class="items-center"):
                        Label("数据库状态：")
                        Badge(status, variant=status_variant)

                    status_display(prefix="db", action="add")

                with Row(gap=2, css_class="justify-end"):
                    button_test(prefix="db", action="add")

                    (
                        Button(
                            "添加",
                            variant="outline",
                            button_type="button",
                            on_click=[
                                SetState("dialog_loading", True),
                                CallTool(
                                    "add_database",
                                    arguments={
                                        "db_name": Rx("db_add_args.db_name"),
                                        "db_config": Rx("db_add_args"),
                                    },
                                    on_success=[
                                        SetState("db_action_result", ""),
                                        SetState("db_add_args.db_name", ""),
                                        SetState("db_add_args", DatabaseConfig().model_dump()),
                                        CallTool(
                                            "get_render_info",
                                            on_success=[
                                                SetState("render_info.db_list", RESULT["db_list"]),
                                                SetState(
                                                    "render_info.db_online_count",
                                                    RESULT["db_online_count"],
                                                ),
                                                SetState(
                                                    "render_info.db_offline_count",
                                                    RESULT["db_offline_count"],
                                                ),
                                                SetState(
                                                    "render_info.db_deactivate_count",
                                                    RESULT["db_deactivate_count"],
                                                ),
                                                SetState(
                                                    "render_info.db_error_count",
                                                    RESULT["db_error_count"],
                                                ),
                                            ],
                                        ),
                                        SetState("db_add_args.status", RESULT.data.status),
                                        SetState("dialog_loading", False),
                                        ShowToast("数据库添加成功"),
                                        CloseOverlay(),
                                    ],
                                    on_error=[
                                        SetState("db_action_result", ERROR),
                                        SetState("db_add_args.status", NodeStatus.Error),
                                        SetState("dialog_loading", False),
                                        ShowToast("数据库添加失败"),
                                    ],
                                ),
                            ],
                        ),
                    )
                    Button(
                        "取消",
                        variant="destructive",
                        on_click=[
                            CloseOverlay(),
                            SetState("db_action_result", ""),
                            SetState("db_add_args.db_name", ""),
                            SetState("db_add_args", DatabaseConfig().model_dump()),
                        ],
                        button_type="button",
                    )

        with Dialog(
            title="编辑数据库", name="edit_db_dialog", css_class="fixed inset-0 bg-black/50"
        ):
            Div()
            with Form():
                with If(Rx("dialog_loading")):
                    with Container(
                        css_class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
                    ):
                        Loader(size="lg")
                with Column(gap=2):
                    Label("数据库类型")
                    with Select(
                        placeholder="选择数据库类型...",
                        name="db_edit_args.db_type",
                        on_change=[
                            SetState("db_edit_args.db_type", EVENT),
                            SetState("db_action_result", ""),
                            CallTool(
                                "switch_default_config",
                                arguments={
                                    "_class": "db",
                                    "_type": Rx("db_edit_args.db_type"),
                                    "config": Rx("db_edit_args"),
                                },
                                on_success=[SetState("db_edit_args", RESULT)],
                            ),
                        ],
                    ):
                        SelectOption(value="sqlite", label="SQLite")
                        SelectOption(value="mysql", label="Mysql")
                        SelectOption(value="postgresql", label="Postgresql")
                        SelectOption(value="influxdb", label="InfluxDB")
                with Column(gap=2):
                    Label("数据库名称")
                    Input(
                        name="db_edit_args.db_name", placeholder="如：mysql-default", required=True
                    )
                with Row(gap=2):
                    with Column(gap=2):
                        Label("数据库地址")
                        Input(
                            name="db_edit_args.db_host",
                            placeholder="如：127.0.0.1",
                            required=True,
                        )
                    with If(Rx("db_edit_args.db_type") != "sqlite"):
                        with Column(gap=2):
                            Label("数据库端口")
                            Input(
                                name="db_edit_args.db_port",
                                placeholder="如：3306",
                                input_type="number",
                            )
                        with If(Rx("db_edit_args.db_type") != "influxdb"):
                            with Column(gap=2):
                                Label("数据库用户名")
                                Input(name="db_edit_args.db_username", placeholder="如：root")
                            with Column(gap=2):
                                Label("数据库密码")
                                Input(
                                    name="db_edit_args.db_password",
                                    placeholder="如：123456",
                                    input_type="password",
                                )
                with If(Rx("db_edit_args.db_type") != "sqlite"):
                    with Column(gap=2):
                        Label("默认数据库")
                        Input(name="db_edit_args.default_database", placeholder="如：service_data")
                with If(Rx("db_edit_args.db_type") == "influxdb"):
                    with Row(gap=2):
                        with Column(gap=2):
                            Label("InfluxDB 令牌")
                            Input(
                                name="db_edit_args.influxdb_token",
                                placeholder="如：token-123abc...",
                                input_type="password",
                            )
                        with Column(gap=2):
                            Label("InfluxDB 组织")
                            Input(name="db_edit_args.influxdb_org", placeholder="如：service_data")
                        with Column(gap=2):
                            Label("InfluxDB 桶")
                            Input(
                                name="db_edit_args.influxdb_bucket", placeholder="如：service_data"
                            )
                with Column(gap=2):
                    Label("连接池大小")
                    Input(
                        name="db_edit_args.db_pool_size",
                        placeholder="如：5",
                        input_type="number",
                    )
                with Column(gap=2):
                    Label("SQL 打印")
                    with Select(
                        name="db_edit_args.db_sql_echo",
                        on_change=[
                            SetState("db_edit_args.db_sql_echo", EVENT),
                        ],
                    ):
                        SelectOption(value="open", label="是")
                        SelectOption(value="close", label="否")
                with Column(gap=2):
                    status, status_variant = get_status_component_args(prefix="db", action="edit")

                    with Row(gap=2, css_class="items-center"):
                        Label("数据库状态：")
                        Badge(status, variant=status_variant)

                    status_display(prefix="db", action="edit")

                with Row(gap=2, css_class="justify-end"):
                    button_test(prefix="db", action="edit")

                    (
                        Button(
                            "保存",
                            variant="outline",
                            button_type="submit",
                            on_click=[
                                SetState("dialog_loading", True),
                                CallTool(
                                    "update_database",
                                    arguments={
                                        "db_name": Rx("db_edit_args.db_old_name"),
                                        "db_config": Rx("db_edit_args"),
                                    },
                                    on_success=[
                                        SetState("db_action_result", ""),
                                        SetState("db_edit_args", {}),
                                        CallTool(
                                            "get_render_info",
                                            on_success=[
                                                SetState("render_info.db_list", RESULT["db_list"]),
                                                SetState(
                                                    "render_info.db_online_count",
                                                    RESULT["db_online_count"],
                                                ),
                                                SetState(
                                                    "render_info.db_offline_count",
                                                    RESULT["db_offline_count"],
                                                ),
                                                SetState(
                                                    "render_info.db_deactivate_count",
                                                    RESULT["db_deactivate_count"],
                                                ),
                                                SetState(
                                                    "render_info.db_error_count",
                                                    RESULT["db_error_count"],
                                                ),
                                            ],
                                        ),
                                        SetState("db_edit_args.status", RESULT.data.status),
                                        SetState("dialog_loading", False),
                                        ShowToast("数据库更新成功"),
                                        SetState("edit_db_dialog", False),
                                        CloseOverlay(),
                                    ],
                                    on_error=[
                                        SetState("db_action_result", ERROR),
                                        SetState("db_edit_args.status", NodeStatus.Error),
                                        SetState("dialog_loading", False),
                                        ShowToast("数据库更新失败"),
                                    ],
                                ),
                            ],
                        ),
                    )
                    with Popover():
                        Button("停用", variant="outline", button_type="button")
                        with Column(gap=2):
                            Text("是否确认停用并保存当前修改？")
                            Button(
                                "确认",
                                on_click=[
                                    SetState("db_edit_args.status", NodeStatus.Deactivate),
                                    SetState("dialog_loading", True),
                                    CallTool(
                                        "update_database",
                                        arguments={
                                            "db_name": Rx("db_edit_args.db_old_name"),
                                            "db_config": Rx("db_edit_args"),
                                        },
                                        on_success=[
                                            SetState("db_action_result", ""),
                                            SetState("db_edit_args", {}),
                                            CallTool(
                                                "get_render_info",
                                                on_success=[
                                                    SetState(
                                                        "render_info.db_list", RESULT["db_list"]
                                                    ),
                                                    SetState(
                                                        "render_info.db_online_count",
                                                        RESULT["db_online_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.db_offline_count",
                                                        RESULT["db_offline_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.db_deactivate_count",
                                                        RESULT["db_deactivate_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.db_error_count",
                                                        RESULT["db_error_count"],
                                                    ),
                                                ],
                                            ),
                                            SetState("db_edit_args.status", RESULT.data.status),
                                            SetState("dialog_loading", False),
                                            ShowToast("数据库停用成功"),
                                            CloseOverlay(),
                                            SetState("edit_db_dialog", False),
                                        ],
                                        on_error=[
                                            SetState("db_action_result", ERROR),
                                            SetState("db_edit_args.status", NodeStatus.Error),
                                            SetState("dialog_loading", False),
                                            ShowToast("数据库停用失败"),
                                        ],
                                    ),
                                ],
                            )
                    with Popover():
                        Button("删除", variant="outline", button_type="button")
                        with Column(gap=2):
                            Text("是否确认删除该数据库？仅删除数据库配置，不删除数据库文件。")
                            Button(
                                "确认",
                                on_click=[
                                    SetState("dialog_loading", True),
                                    CallTool(
                                        "delete_database",
                                        arguments={
                                            "db_name": Rx("db_edit_args.db_old_name"),
                                        },
                                        on_success=[
                                            SetState("db_action_result", ""),
                                            SetState("db_edit_args", {}),
                                            CallTool(
                                                "get_render_info",
                                                on_success=[
                                                    SetState(
                                                        "render_info.db_list", RESULT["db_list"]
                                                    ),
                                                    SetState(
                                                        "render_info.db_online_count",
                                                        RESULT["db_online_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.db_offline_count",
                                                        RESULT["db_offline_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.db_deactivate_count",
                                                        RESULT["db_deactivate_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.db_error_count",
                                                        RESULT["db_error_count"],
                                                    ),
                                                ],
                                            ),
                                            SetState("db_edit_args.status", RESULT.data.status),
                                            SetState("dialog_loading", False),
                                            ShowToast("数据库删除成功"),
                                            CloseOverlay(),
                                            SetState("edit_db_dialog", False),
                                        ],
                                        on_error=[
                                            SetState("db_action_result", ERROR),
                                            SetState("db_edit_args.status", NodeStatus.Error),
                                            SetState("dialog_loading", False),
                                            ShowToast("数据库删除失败"),
                                        ],
                                    ),
                                ],
                            )
                    Button(
                        "取消",
                        variant="destructive",
                        on_click=[
                            CloseOverlay(),
                            SetState("db_action_result", ""),
                            SetState("db_edit_args", {}),
                        ],
                        button_type="button",
                    )

        with Dialog(
            title="添加缓存", name="add_cache_dialog", css_class="fixed inset-0 bg-black/50"
        ):
            Div()
            with Form():
                with If(Rx("dialog_loading")):
                    with Container(
                        css_class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
                    ):
                        Loader(size="lg")
                with Column(gap=2):
                    Label("数据库类型")
                    with Select(
                        disabled=True,
                        placeholder="选择数据库类型...",
                        name="cache_add_args.cache_type",
                        on_change=[
                            SetState("cache_add_args.cache_type", EVENT),
                            SetState("cache_action_result", ""),
                            CallTool(
                                "switch_default_config",
                                arguments={
                                    "_class": "cache",
                                    "_type": Rx("cache_add_args.cache_type"),
                                    "config": Rx("cache_add_args.cache_name"),
                                },
                                on_success=[SetState("cache_add_args", RESULT)],
                            ),
                        ],
                    ):
                        SelectOption(value="redis", label="Redis", selected=True)
                with Column(gap=2):
                    Label("数据库名称")
                    Input(
                        name="cache_add_args.cache_name",
                        placeholder="如：redis-default",
                        required=True,
                    )
                with Row(gap=2):
                    with Column(gap=2):
                        Label("缓存主机地址")
                        Input(
                            name="cache_add_args.cache_host",
                            placeholder="如：127.0.0.1",
                            required=True,
                        )
                    with Column(gap=2):
                        Label("缓存端口")
                        Input(
                            name="cache_add_args.cache_port",
                            placeholder="如：6339",
                            input_type="number",
                        )
                    with Column(gap=2):
                        Label("缓存密码")
                        Input(
                            name="cache_add_args.cache_pass",
                            placeholder="如：123456",
                            input_type="password",
                        )
                with Row(gap=2):
                    with Column(gap=2):
                        Label("超时时间")
                        Input(
                            name="cache_add_args.timeout", placeholder="如：5", input_type="number"
                        )
                    with Column(gap=2):
                        Label("缓存过期时间（秒）")
                        Input(
                            name="cache_add_args.ttl_seconds",
                            placeholder="如：300",
                            input_type="number",
                        )
                    with Column(gap=2):
                        Label("缓存最大大小（MB）")
                        Input(
                            name="cache_add_args.max_size",
                            placeholder="如：1024",
                            input_type="number",
                        )
                with Row(gap=2):
                    with Column(gap=2):
                        Label("数据库数量")
                        Input(
                            name="cache_add_args.databases",
                            placeholder="如：16",
                            input_type="number",
                            required=True,
                        )
                    with Column(gap=2):
                        Label("主数据库索引")
                        Input(
                            name="cache_add_args.cache_main",
                            placeholder="如：0",
                            input_type="number",
                            required=True,
                        )
                    with Column(gap=2):
                        Label("连接池大小")
                        Input(
                            name="cache_add_args.cache_pool_size",
                            placeholder="如：5",
                            input_type="number",
                            required=True,
                        )
                with Column(gap=2):
                    Label("键前缀")
                    Input(name="cache_add_args.key_prefix", placeholder="如：key")

                with Column(gap=2):
                    status, status_variant = get_status_component_args(prefix="cache", action="add")

                    with Row(gap=2, css_class="items-center"):
                        Label("数据库状态：")
                        Badge(status, variant=status_variant)

                    status_display(prefix="cache", action="add")

                with Row(gap=2, css_class="justify-end"):
                    button_test(prefix="cache", action="add")

                    (
                        Button(
                            "添加",
                            variant="outline",
                            button_type="button",
                            on_click=[
                                SetState("dialog_loading", True),
                                CallTool(
                                    "add_cache",
                                    arguments={
                                        "cache_name": Rx("cache_add_args.cache_name"),
                                        "cache_config": Rx("cache_add_args"),
                                    },
                                    on_success=[
                                        SetState("cache_action_result", ""),
                                        SetState("cache_add_args.cache_name", ""),
                                        SetState("cache_add_args", CacheConfig().model_dump()),
                                        CallTool(
                                            "get_render_info",
                                            on_success=[
                                                SetState(
                                                    "render_info.cache_list", RESULT["cache_list"]
                                                ),
                                                SetState(
                                                    "render_info.cache_online_count",
                                                    RESULT["cache_online_count"],
                                                ),
                                                SetState(
                                                    "render_info.cache_offline_count",
                                                    RESULT["cache_offline_count"],
                                                ),
                                                SetState(
                                                    "render_info.cache_deactivate_count",
                                                    RESULT["cache_deactivate_count"],
                                                ),
                                                SetState(
                                                    "render_info.cache_error_count",
                                                    RESULT["cache_error_count"],
                                                ),
                                            ],
                                        ),
                                        SetState("cache_edit_args.status", RESULT.data.status),
                                        SetState("dialog_loading", False),
                                        ShowToast("缓存添加成功"),
                                        CloseOverlay(),
                                    ],
                                    on_error=[
                                        SetState("cache_action_result", ERROR),
                                        SetState("cache_edit_args.status", NodeStatus.Error),
                                        SetState("dialog_loading", False),
                                        ShowToast("缓存添加失败"),
                                    ],
                                ),
                            ],
                        ),
                    )
                    Button(
                        "取消",
                        variant="destructive",
                        on_click=[
                            CloseOverlay(),
                            SetState("cache_action_result", ""),
                            SetState("cache_add_args.cache_name", ""),
                            SetState("cache_add_args", CacheConfig().model_dump()),
                        ],
                        button_type="button",
                    )

        with Dialog(
            title="编辑缓存", name="edit_cache_dialog", css_class="fixed inset-0 bg-black/50"
        ):
            Div()
            with Form():
                with If(Rx("dialog_loading")):
                    with Container(
                        css_class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
                    ):
                        Loader(size="lg")
                with Column(gap=2):
                    Label("缓存类型")
                    with Select(
                        disabled=True,
                        placeholder="选择缓存类型...",
                        name="cache_edit_args.cache_type",
                        on_change=[
                            SetState("cache_edit_args.cache_type", EVENT),
                            SetState("cache_action_result", ""),
                            CallTool(
                                "switch_default_config",
                                arguments={
                                    "_class": "cache",
                                    "_type": Rx("cache_edit_args.cache_type"),
                                    "config": Rx("cache_edit_args"),
                                },
                                on_success=[SetState("cache_edit_args", RESULT)],
                            ),
                        ],
                    ):
                        SelectOption(value="redis", label="Redis", selected=True)
                with Column(gap=2):
                    Label("数据库名称")
                    Input(
                        name="cache_edit_args.cache_name",
                        placeholder="如：redis-default",
                        required=True,
                    )
                with Row(gap=2):
                    with Column(gap=2):
                        Label("缓存主机地址")
                        Input(
                            name="cache_edit_args.cache_host",
                            placeholder="如：127.0.0.1",
                            required=True,
                        )
                    with Column(gap=2):
                        Label("缓存端口")
                        Input(
                            name="cache_edit_args.cache_port",
                            placeholder="如：6339",
                            input_type="number",
                        )
                    with Column(gap=2):
                        Label("缓存密码")
                        Input(name="cache_edit_args.cache_pass", placeholder="如：123456")
                with Row(gap=2):
                    with Column(gap=2):
                        Label("超时时间")
                        Input(
                            name="cache_edit_args.timeout", placeholder="如：5", input_type="number"
                        )
                    with Column(gap=2):
                        Label("缓存过期时间（秒）")
                        Input(
                            name="cache_edit_args.ttl_seconds",
                            placeholder="如：300",
                            input_type="number",
                        )
                    with Column(gap=2):
                        Label("缓存最大大小（MB）")
                        Input(
                            name="cache_edit_args.max_size",
                            placeholder="如：1024",
                            input_type="number",
                        )
                with Row(gap=2):
                    with Column(gap=2):
                        Label("数据库数量")
                        Input(
                            name="cache_edit_args.databases",
                            placeholder="如：16",
                            input_type="number",
                            required=True,
                        )
                    with Column(gap=2):
                        Label("主数据库索引")
                        Input(
                            name="cache_edit_args.cache_main",
                            placeholder="如：0",
                            input_type="number",
                            required=True,
                        )
                    with Column(gap=2):
                        Label("连接池大小")
                        Input(
                            name="cache_edit_args.cache_pool_size",
                            placeholder="如：5",
                            input_type="number",
                            required=True,
                        )
                with Column(gap=2):
                    Label("键前缀")
                    Input(name="cache_edit_args.key_prefix", placeholder="如：key")

                with Column(gap=2):
                    status, status_variant = get_status_component_args(
                        prefix="cache", action="edit"
                    )

                    with Row(gap=2, css_class="items-center"):
                        Label("数据库状态：")
                        Badge(status, variant=status_variant)

                    status_display(prefix="cache", action="edit")

                with Row(gap=2, css_class="justify-end"):
                    button_test(prefix="cache", action="edit")

                    (
                        Button(
                            "保存",
                            variant="outline",
                            button_type="submit",
                            on_click=[
                                SetState("dialog_loading", True),
                                CallTool(
                                    "update_cache",
                                    arguments={
                                        "cache_name": Rx("cache_edit_args.cache_old_name"),
                                        "cache_config": Rx("cache_edit_args"),
                                    },
                                    on_success=[
                                        SetState("cache_action_result", ""),
                                        SetState("cache_edit_args", {}),
                                        CallTool(
                                            "get_render_info",
                                            on_success=[
                                                SetState(
                                                    "render_info.cache_list", RESULT["cache_list"]
                                                ),
                                                SetState(
                                                    "render_info.cache_online_count",
                                                    RESULT["cache_online_count"],
                                                ),
                                                SetState(
                                                    "render_info.cache_offline_count",
                                                    RESULT["cache_offline_count"],
                                                ),
                                                SetState(
                                                    "render_info.cache_deactivate_count",
                                                    RESULT["cache_deactivate_count"],
                                                ),
                                                SetState(
                                                    "render_info.cache_error_count",
                                                    RESULT["cache_error_count"],
                                                ),
                                            ],
                                        ),
                                        SetState("cache_edit_args.status", RESULT.data.status),
                                        SetState("dialog_loading", False),
                                        ShowToast("缓存更新成功"),
                                        SetState("edit_cache_dialog", False),
                                        CloseOverlay(),
                                    ],
                                    on_error=[
                                        SetState("cache_action_result", ERROR),
                                        SetState("cache_edit_args.status", NodeStatus.Error),
                                        SetState("dialog_loading", False),
                                        ShowToast("缓存更新失败"),
                                    ],
                                ),
                            ],
                        ),
                    )
                    with Popover():
                        Button("停用", variant="outline", button_type="button")
                        with Column(gap=2):
                            Text("是否确认停用并保存当前修改？")
                            Button(
                                "确认",
                                on_click=[
                                    SetState("cache_edit_args.status", NodeStatus.Deactivate),
                                    SetState("dialog_loading", True),
                                    CallTool(
                                        "update_cache",
                                        arguments={
                                            "cache_name": Rx("cache_edit_args.cache_old_name"),
                                            "cache_config": Rx("cache_edit_args"),
                                        },
                                        on_success=[
                                            SetState("cache_action_result", ""),
                                            SetState("cache_edit_args", {}),
                                            CallTool(
                                                "get_render_info",
                                                on_success=[
                                                    SetState(
                                                        "render_info.cache_list",
                                                        RESULT["cache_list"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_online_count",
                                                        RESULT["cache_online_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_offline_count",
                                                        RESULT["cache_offline_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_deactivate_count",
                                                        RESULT["cache_deactivate_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_error_count",
                                                        RESULT["cache_error_count"],
                                                    ),
                                                ],
                                            ),
                                            SetState("cache_edit_args.status", RESULT.data.status),
                                            SetState("dialog_loading", False),
                                            ShowToast("缓存停用成功"),
                                            CloseOverlay(),
                                            SetState("edit_cache_dialog", False),
                                        ],
                                        on_error=[
                                            SetState("cache_action_result", ERROR),
                                            SetState("cache_edit_args.status", NodeStatus.Error),
                                            SetState("dialog_loading", False),
                                            ShowToast("缓存停用失败"),
                                        ],
                                    ),
                                ],
                            )
                    with Popover():
                        Button("删除", variant="outline", button_type="button")
                        with Column(gap=2):
                            Text("是否确认删除该缓存？仅删除缓存配置，不删除缓存文件。")
                            Button(
                                "确认",
                                on_click=[
                                    SetState("dialog_loading", True),
                                    CallTool(
                                        "delete_cache",
                                        arguments={
                                            "cache_name": Rx("cache_edit_args.cache_old_name"),
                                        },
                                        on_success=[
                                            SetState("cache_action_result", ""),
                                            SetState("cache_edit_args", {}),
                                            CallTool(
                                                "get_render_info",
                                                on_success=[
                                                    SetState(
                                                        "render_info.cache_list",
                                                        RESULT["cache_list"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_online_count",
                                                        RESULT["cache_online_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_offline_count",
                                                        RESULT["cache_offline_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_deactivate_count",
                                                        RESULT["cache_deactivate_count"],
                                                    ),
                                                    SetState(
                                                        "render_info.cache_error_count",
                                                        RESULT["cache_error_count"],
                                                    ),
                                                ],
                                            ),
                                            SetState("dialog_loading", False),
                                            ShowToast("缓存删除成功"),
                                            CloseOverlay(),
                                            SetState("edit_cache_dialog", False),
                                        ],
                                        on_error=[
                                            SetState("cache_action_result", ERROR),
                                            SetState("dialog_loading", False),
                                            ShowToast("缓存删除失败"),
                                        ],
                                    ),
                                ],
                            )
                    Button(
                        "取消",
                        variant="destructive",
                        on_click=[
                            CloseOverlay(),
                            SetState("cache_action_result", ""),
                            SetState("cache_edit_args", {}),
                        ],
                        button_type="button",
                    )

        with DashboardItem(col=1, row=1, col_span=12, row_span=2):
            with Card(css_class="h-full"):
                with CardHeader():
                    H1("配置工具", css_class="text-3xl font-bold")
                with CardContent():
                    Muted("描述：提供MCP服务器的配置管理功能，包括数据库、缓存等。")

        with DashboardItem(col=1, row=3, col_span=8, row_span=3):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    with Row(css_class="justify-between"):
                        CardTitle("数据库配置")
                        Button("添加数据库", icon="plus", on_click=SetState("add_db_dialog", True))
                with CardContent():
                    DataTable(
                        columns=[
                            DataTableColumn(key="db_name", header="数据库名称", align="center"),
                            DataTableColumn(key="db_type", header="数据库类型", align="center"),
                            DataTableColumn(key="db_host", header="数据库地址", align="center"),
                            DataTableColumn(key="db_port", header="数据库端口", align="center"),
                            DataTableColumn(
                                key="db_username", header="数据库用户名", align="center"
                            ),
                            DataTableColumn(key="db_main", header="默认数据库", align="center"),
                            DataTableColumn(
                                key="status_component", header="数据库状态", align="center"
                            ),
                        ],
                        rows=Rx("render_info.db_list"),
                        paginated=True,
                        page_size=5,
                        search=True,
                        on_row_click=[
                            SetState(
                                "db_edit_args",
                                {
                                    "db_old_name": EVENT.db_name,
                                    "db_name": EVENT.db_name,
                                    "db_type": EVENT.db_type,
                                    "db_host": EVENT.db_host,
                                    "db_port": EVENT.db_port,
                                    "db_username": EVENT.db_username,
                                    "db_password": EVENT.db_password,
                                    "db_main": EVENT.db_main,
                                    "db_sql_echo": EVENT.db_sql_echo,
                                    "db_pool_size": EVENT.db_pool_size,
                                    "influxdb_token": EVENT.influxdb_token,
                                    "influxdb_org": EVENT.influxdb_org,
                                    "influxdb_bucket": EVENT.influxdb_bucket,
                                    "status": EVENT.status,
                                },
                            ),
                            SetState("edit_db_dialog", True),
                            SetState("db_action_result", ""),
                        ],
                    )

        with DashboardItem(col=9, row=3, col_span=4):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    Muted("在线/离线/总数据库数量")
                with CardContent():
                    H2(
                        f"{Rx('render_info.db_online_count')}/{Rx('render_info.db_offline_count')}/{Rx('render_info.db_total_count')}"
                    )

        with DashboardItem(col=9, row=4, col_span=4):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    Muted("停用数据库数量")
                with CardContent():
                    H2(str(Rx("render_info.db_deactivate_count")))

        with DashboardItem(col=9, row=5, col_span=4):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    Muted("未知/故障数据库数量")
                with CardContent():
                    H2(f"{Rx('render_info.db_unknown_count')}/{Rx('render_info.db_error_count')}")

        with DashboardItem(col=1, row=6, col_span=8, row_span=3):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    with Row(css_class="justify-between"):
                        CardTitle("缓存配置")
                        Button("添加缓存", icon="plus", on_click=SetState("add_cache_dialog", True))
                with CardContent():
                    DataTable(
                        columns=[
                            DataTableColumn(key="cache_name", header="缓存名称", align="center"),
                            DataTableColumn(key="cache_host", header="缓存地址", align="center"),
                            DataTableColumn(
                                key="cache_port", header="缓存端口", align="center", format="number"
                            ),
                            DataTableColumn(
                                key="cache_main",
                                header="主数据库索引",
                                align="center",
                                format="number",
                            ),
                            DataTableColumn(
                                key="databases",
                                header="逻辑数据库数量",
                                align="center",
                                format="number",
                            ),
                            DataTableColumn(key="key_prefix", header="键前缀", align="center"),
                            DataTableColumn(
                                key="ttl_seconds",
                                header="缓存过期时间（秒）",
                                align="center",
                                format="number",
                            ),
                            DataTableColumn(
                                key="max_size",
                                header="最大缓存大小（MB）",
                                align="center",
                                format="number",
                            ),
                            DataTableColumn(
                                key="cache_pool_size",
                                header="连接池数量",
                                align="center",
                                format="number",
                            ),
                            DataTableColumn(
                                key="status_component", header="缓存状态", align="center"
                            ),
                        ],
                        rows=Rx("render_info.cache_list"),
                        paginated=True,
                        page_size=5,
                        search=True,
                        on_row_click=[
                            SetState(
                                "cache_edit_args",
                                {
                                    "cache_old_name": EVENT.cache_name,
                                    "cache_name": EVENT.cache_name,
                                    "cache_host": EVENT.cache_host,
                                    "cache_port": EVENT.cache_port,
                                    "cache_pass": EVENT.cache_pass,
                                    "timeout": EVENT.timeout,
                                    "cache_main": EVENT.cache_main,
                                    "databases": EVENT.databases,
                                    "key_prefix": EVENT.key_prefix,
                                    "ttl_seconds": EVENT.ttl_seconds,
                                    "max_size": EVENT.max_size,
                                    "status": EVENT.status,
                                    "cache_type": EVENT.cache_type,
                                    "cache_pool_size": EVENT.cache_pool_size,
                                },
                            ),
                            SetState("edit_cache_dialog", True),
                            SetState("db_action_result", ""),
                        ],
                    )

        with DashboardItem(col=9, row=6, col_span=4):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    Muted("在线/离线/总缓存数量")
                with CardContent():
                    H2(
                        f"{Rx('render_info.cache_online_count')}/{Rx('render_info.cache_offline_count')}/{Rx('render_info.cache_total_count')}"
                    )

        with DashboardItem(col=9, row=7, col_span=4):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    Muted("停用缓存数量")
                with CardContent():
                    H2(str(Rx("render_info.cache_deactivate_count")))

        with DashboardItem(col=9, row=8, col_span=4):
            with Card(css_class="h-full"):
                with CardHeader(css_class="pb-2"):
                    Muted("未知/故障缓存数量")
                with CardContent():
                    H2(
                        f"{Rx('render_info.cache_unknown_count')}/{Rx('render_info.cache_error_count')}"
                    )

    return PrefabApp(
        view=dashboard,
        state={
            "render_info": {
                "db_list": [],
                "cache_list": [],
                "db_online_count": 0,
                "db_offline_count": 0,
                "db_error_count": 0,
                "db_deactivate_count": 0,
                "db_unknown_count": 0,
                "db_total_count": 0,
                "cache_online_count": 0,
                "cache_offline_count": 0,
                "cache_error_count": 0,
                "cache_deactivate_count": 0,
                "cache_unknown_count": 0,
                "cache_total_count": 0,
            },
            "db_add_args": {
                "db_name": "",
                "db_type": "sqlite",
                "db_host": "memory",
                "db_port": 0,
                "db_username": "",
                "db_password": "",
                "db_sql_echo": "close",
                "db_pool_size": 5,
                "status": NodeStatus.Unknown,
            },
            "db_edit_args": {},
            "cache_add_args": {
                "cache_name": "",
                "cache_host": "127.0.0.1",
                "cache_port": 6379,
                "cache_pass": "",
                "timeout": 5,
                "cache_main": 0,
                "databases": 16,
                "key_prefix": "",
                "ttl_seconds": 300,
                "max_size": 1024,
                "cache_pool_size": 5,
                "status": NodeStatus.Unknown,
                "cache_type": "redis",
            },
            "cache_edit_args": {},
            "db_action_result": "",
            "cache_action_result": "",
            "dialog_loading": False,
            "add_db_dialog": False,
            "add_cache_dialog": False,
            "edit_db_dialog": False,
            "edit_cache_dialog": False,
        },
        on_mount=[
            CallTool(
                "get_render_info",
                on_success=[
                    SetState("render_info", RESULT),
                ],
            )
        ],
    )
