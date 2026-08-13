class DatabaseConnectionError(Exception):
    """数据库连接错误"""


class UniqueConflictError(ValueError):
    """唯一性冲突错误（来自 _check_own_codes_unique）"""
