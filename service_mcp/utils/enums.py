__all__ = [
    "AbnormalType",
    "AuthAction",
    "AuthResource",
    "BaseEnum",
    "DataScope",
    "EntityType",
    "Errcode",
    "NodeStatus",
    "ProductDataSource",
    "ProductStatus",
    "ProductType",
    "PublishStatus",
]

from enum import Enum
from typing import Any, cast

from prefab_ui.components import Badge
from starlette.status import (
    HTTP_200_OK,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_408_REQUEST_TIMEOUT,
    HTTP_409_CONFLICT,
    HTTP_422_UNPROCESSABLE_CONTENT,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_501_NOT_IMPLEMENTED,
    HTTP_502_BAD_GATEWAY,
    HTTP_503_SERVICE_UNAVAILABLE,
    HTTP_504_GATEWAY_TIMEOUT,
)


class BaseEnum(Enum):
    """通用枚举基类（参考 codes.py 格式）。

    成员格式：(value, label, *extras)。底层实例由 ``object.__new__`` 创建，
    额外属性在子类 ``__init__`` 中通过 ``object.__setattr__`` 设置
    （枚举成员只读，常规赋值会被拦截）。

    子类可在类体末尾设置 ``_default`` 成员，未匹配值将兜底返回该成员。
    """

    label: str

    def __new__(cls, value: Any, label: str, *_extras):
        obj = object.__new__(cls)
        obj._value_ = value
        obj.label = label
        return obj

    def __str__(self):
        return f"{self.value}"

    def __int__(self) -> int:
        """int(枚举) → 枚举值，兼容 int 字段绑定（Pydantic/SQLAlchemy）。"""
        return int(self.value)

    def __index__(self) -> int:
        """索引协议，兼容 sqlite3 / 序列化对 int 的要求。"""
        return int(self.value)

    def __eq__(self, other: object) -> bool:
        """与同枚举成员或裸值（int/str）按 value 比较，兼容 ``code == Errcode.SUCCESS`` 等写法。"""
        if isinstance(other, BaseEnum):
            return self.value == other.value
        if isinstance(other, (int, str)):
            return self.value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.value)

    @classmethod
    def _get_default(cls) -> "BaseEnum | None":
        """返回子类设置的 _default 成员，未设置则为 None。"""
        return getattr(cls, "_default", None)

    @classmethod
    def _resolver(cls, value: Any, default: "BaseEnum | None" = None) -> "BaseEnum | None":
        """按 value / label / 成员名 安全查找成员。"""
        if isinstance(value, (int, str)):
            for m in cls:
                if m.value == value:
                    return m
        if isinstance(value, str):
            for m in cls:
                if m.label == value or m.name.lower() == value.lower():
                    return m
        return default

    @classmethod
    def _missing_(cls, value: Any) -> "BaseEnum | None":
        return cls._resolver(value, default=cls._get_default())

    @classmethod
    def from_name(cls, name: str) -> "BaseEnum | None":
        return cls._resolver(name, default=cls._get_default())

    @classmethod
    def from_value(cls, value: Any) -> "BaseEnum | None":
        """按枚举值安全查找成员，未找到返回 None（不抛异常）。"""
        return cast("BaseEnum | None", cls._value2member_map_.get(value))


class Errcode(BaseEnum):
    """
    API 错误代码枚举，第一个值为错误码，第二个值为标签，第三个值为 HTTP 状态码。
    格式: A BB CCC
    - A：错误级别（-4 客户端错误，-5 服务端错误，-9 第三方）
    - BB：模块编号（见下表）
    - CCC：具体错误编号（从 001 开始）

    模块编号分配
    BB	模块名
    00	通用
    10	工具（Tools）
    11	资源（Resources）
    12	提示词（Prompts）
    13	会话与连接
    14	认证与授权
    20	数据库（存储）
    21	缓存
    30	第三方服务
    """

    http: int

    def __init__(self, value: Any, label: str, http: int = HTTP_200_OK, *_extras):
        object.__setattr__(self, "http", http)

    # 通用错误码
    PROCESS = 3, "处理中", HTTP_200_OK
    CONTINUE = 2, "继续", HTTP_200_OK
    DONE = 1, "完成", HTTP_200_OK
    SUCCESS = 0, "成功", HTTP_200_OK
    FAIL = -1, "失败", HTTP_500_INTERNAL_SERVER_ERROR

    MCP_INTERNAL_ERROR = -500000, "MCP 内部错误", HTTP_500_INTERNAL_SERVER_ERROR
    MCP_NOT_IMPLEMENTED = -500001, "功能未实现", HTTP_501_NOT_IMPLEMENTED
    MCP_BAD_REQUEST = -400000, "MCP 请求格式错误", HTTP_400_BAD_REQUEST

    # 客户端错误
    TOOL_NOT_FOUND = -410001, "工具不存在", HTTP_404_NOT_FOUND
    TOOL_INVALID_PARAMS = -410002, "工具参数无效", HTTP_422_UNPROCESSABLE_CONTENT
    TOOL_MISSING_REQUIRED_PARAM = -410003, "缺少必需参数", HTTP_422_UNPROCESSABLE_CONTENT
    TOOL_EXECUTION_NOT_ALLOWED = -410004, "不允许执行该工具", HTTP_403_FORBIDDEN
    BUSINESS_FAILED = -410005, "业务校验失败", HTTP_400_BAD_REQUEST

    # 服务端错误
    TOOL_EXECUTION_FAILED = -510001, "工具执行失败", HTTP_500_INTERNAL_SERVER_ERROR
    TOOL_TIMEOUT = -510002, "工具执行超时", HTTP_504_GATEWAY_TIMEOUT
    TOOL_CONFIG_ERROR = -510003, "工具配置错误", HTTP_500_INTERNAL_SERVER_ERROR

    # 资源错误
    RESOURCE_NOT_FOUND = -511001, "资源不存在", HTTP_404_NOT_FOUND
    RESOURCE_LOAD_FAILED = -511002, "资源加载失败", HTTP_500_INTERNAL_SERVER_ERROR
    RESOURCE_PERMISSION_DENIED = -411003, "无权限访问资源", HTTP_403_FORBIDDEN
    RESOURCE_URI_INVALID = -411004, "资源 URI 格式无效", HTTP_400_BAD_REQUEST

    # 提示词错误
    PROMPT_NOT_FOUND = -512001, "提示词模板不存在", HTTP_404_NOT_FOUND
    PROMPT_RENDER_FAILED = -512002, "提示词渲染失败", HTTP_500_INTERNAL_SERVER_ERROR
    PROMPT_INVALID_ARGUMENTS = -412003, "提示词参数无效", HTTP_422_UNPROCESSABLE_CONTENT

    # 会话与连接错误
    SESSION_NOT_INITIALIZED = -413001, "会话未初始化", HTTP_400_BAD_REQUEST
    SESSION_TIMEOUT = -413002, "会话已超时", HTTP_408_REQUEST_TIMEOUT
    CONNECTION_ERROR = -513003, "底层连接错误", HTTP_502_BAD_GATEWAY
    CLIENT_DISCONNECTED = -413004, "客户端已断开", HTTP_400_BAD_REQUEST

    # 认证与授权错误
    AUTH_FAILED = -414001, "认证失败", HTTP_401_UNAUTHORIZED
    AUTH_TOKEN_EXPIRED = -414002, "认证令牌已过期", HTTP_401_UNAUTHORIZED
    AUTH_INSUFFICIENT_SCOPE = -414003, "权限范围不足", HTTP_403_FORBIDDEN

    # 数据库错误
    DB_CONNECTION_FAILED = -520001, "数据库连接失败", HTTP_503_SERVICE_UNAVAILABLE
    DB_QUERY_FAILED = -520002, "数据库查询失败", HTTP_500_INTERNAL_SERVER_ERROR
    DB_TIMEOUT = -520003, "数据库操作超时", HTTP_504_GATEWAY_TIMEOUT
    DB_TRANSACTION_ERROR = -520004, "数据库事务错误", HTTP_500_INTERNAL_SERVER_ERROR
    DB_INTEGRITY_ERROR = -520005, "数据完整性错误", HTTP_409_CONFLICT

    UNIQUE_CONFLICT = -420006, "数据唯一性冲突", HTTP_409_CONFLICT
    RECORD_NOT_FOUND = -420007, "记录不存在", HTTP_404_NOT_FOUND

    # 缓存错误
    CACHE_CONNECTION_FAILED = -521001, "缓存连接失败", HTTP_503_SERVICE_UNAVAILABLE
    CACHE_WRITE_FAILED = -521002, "缓存写入失败", HTTP_500_INTERNAL_SERVER_ERROR
    CACHE_TIMEOUT = -521003, "缓存操作超时", HTTP_504_GATEWAY_TIMEOUT
    CACHE_SERIALIZATION_ERROR = -521004, "缓存序列化错误", HTTP_500_INTERNAL_SERVER_ERROR

    # 第三方服务错误
    THIRD_PARTY_ERROR = -930001, "第三方服务错误", HTTP_502_BAD_GATEWAY
    THIRD_PARTY_TIMEOUT = -930002, "第三方服务超时", HTTP_504_GATEWAY_TIMEOUT
    THIRD_PARTY_INVALID_RESPONSE = -930003, "第三方返回无效响应", HTTP_502_BAD_GATEWAY


class AuthResource(BaseEnum):
    """权限资源码（mcp_perm 的 resource 参数）"""

    Product = "01", "产品"
    ProductPrice = "02", "产品价格"
    Config = "07", "配置"
    Audit = "08", "审计"


class AuthAction(BaseEnum):
    """权限操作码（mcp_perm 的 action 参数）"""

    List = "01", "列表"
    Detail = "02", "详情"
    Create = "03", "新增"
    Update = "04", "修改"
    Delete = "06", "删除"
    Manage = "07", "管理"
    Read = "08", "查看"


class NodeStatus(BaseEnum):
    """节点状态枚举（component 为 prefab UI 徽章配置）"""

    component: dict[str, Any]

    def __init__(self, value: Any, label: str, component: dict[str, Any] | None = None, *_extras):
        object.__setattr__(self, "component", component or {})

    Active = "已启动", "success", Badge("已启动", variant="success").model_dump()
    Inactive = "未启动", "outline", Badge("未启动", variant="outline").model_dump()
    AuthFailed = "授权失败", "outline", Badge("授权失败", variant="outline").model_dump()
    Deactivate = "停用", "secondary", Badge("停用", variant="secondary").model_dump()
    Error = "故障", "destructive", Badge("故障", variant="destructive").model_dump()
    Unknown = "未知", "warning", Badge("未知", variant="warning").model_dump()

    @classmethod
    def _missing_(cls, value: Any) -> "NodeStatus":
        return cls.Unknown


class ProductStatus(BaseEnum):
    """产品状态枚举（示例实体）"""

    Active = 1, "正常"
    Inactive = 2, "停用"
    Unknown = 0, "未知"
    _default = Unknown


class ProductType(BaseEnum):
    """产品类型枚举（示例实体）"""

    Unknown = 0, "未知"
    Equity = 1, "权益类"
    Bond = 2, "固收类"
    Commodity = 3, "商品类"
    Other = 99, "其他"
    _default = Unknown


class ProductDataSource(BaseEnum):
    """产品数据来源枚举（示例实体）"""

    Unknown = 0, "未知"
    ManualImport = 1, "手动导入"
    Api = 2, "API 同步"
    Other = 999, "其他"
    _default = Other


class EntityType(BaseEnum):
    """实体类型枚举（示例实体）"""

    Product = 1, "产品"
    ProductPrice = 2, "产品价格"

    @classmethod
    def from_model_name(cls, model_name: str) -> "EntityType | None":
        """从模型类名获取实体类型枚举"""
        target = model_name.lower()
        return next((m for m in cls if m.name.lower() == target), None)


class DataScope(BaseEnum):
    """数据范围（三级：平台 / 部门 / 个人），配合 scope_visibility_where 使用。

    - platform：平台共享（存量/系统数据；发布审核通过后对全体登录用户可见）
    - team：部门（团队）数据，team_ids 命中的成员可见
    - personal：个人数据（仅归属者本人可见 —— 创始管理员也不可见，安全底线）
    """

    Platform = "platform", "平台"
    Team = "team", "部门"
    Personal = "personal", "个人"
    _default = Platform


class PublishStatus(BaseEnum):
    """数据发布审核状态（针对平台数据：审核通过后才对平台公开）。

    - APPROVED：已审核通过，按 data_scope 正常可见
    - PENDING：待审核，仅归属者（owner_id）可见
    - REJECTED：已拒绝，仅归属者可见
    """

    Pending = "PENDING", "待审核"
    Approved = "APPROVED", "已审核"
    Rejected = "REJECTED", "已拒绝"
    _default = Approved


class AbnormalType(BaseEnum):
    """通用异常标记枚举。NULL/None 表示正常，非 None 表示异常。

    适用于所有 ORM 模型的 abnormal 字段：
      - Product: 关联记录已删除（Orphaned）、占位记录（Placeholder）
      - ProductPrice: 关联产品已删除（Orphaned）、同日同源价格冲突需人工审核（PriceConflict）
    """

    severity: str

    def __init__(self, value: Any, label: str, severity: str = "warning", *_extras):
        object.__setattr__(self, "severity", severity)

    Placeholder = 0, "占位记录", "warning"
    Orphaned = 2, "关联记录已删除", "critical"
    NameMismatch = 3, "名称不一致", "warning"
    PriceConflict = 4, "价格数据冲突，需人工审核", "critical"
