from service_mcp.utils.enums import Errcode


class DatabaseConnectionError(Exception):
    """数据库连接错误"""


class UniqueConflictError(ValueError):
    """唯一性冲突错误（来自 _check_own_codes_unique）"""


class ToolError(ValueError):
    """业务级可预期失败（业务校验失败/越权/资源冲突/记录未找到等）。

    与数据库/程序错误区分：业务规则可放心 raise，由工具转换层统一转换为带
    中文 message 的业务失败响应（UtilResponse + 业务 Errcode），绝不 500 化。
    继承 ValueError 是有意为之：保持既有调用方/测试按 ValueError 兜底与断言
    的兼容；与 UniqueConflictError 保持独立类型，互不误收窄。

    Attributes:
        message: 面向用户的中文错误描述。
        code: 业务错误码，默认 BUSINESS_FAILED；越权/未找到等场景可显式指定。
    """

    def __init__(self, message: str, code: Errcode = Errcode.BUSINESS_FAILED):
        super().__init__(message)
        self.message = message
        self.code = code
