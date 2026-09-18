"""ToolAnnotations 预设常量 — 供 CRUD/查询/导出工具注解复用。

readOnly/destructive/idempotent 组合语义：本仓工具全部只作用于本地数据库
（无外部世界副作用），故 openWorldHint 统一为 False。客户端可据此安全地
对只读工具做缓存/重放，对破坏性工具做确认提示。
"""

__all__ = ["READ_ONLY", "WRITE_DESTRUCTIVE", "WRITE_IDEMPOTENT", "WRITE_MUTATING"]

from mcp.types import ToolAnnotations


# 只读查询/导出：不改状态，天然幂等（客户端可安全重放/缓存）
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

# 新增类写入：非破坏，语义幂等（重复执行不产生额外副作用，唯一冲突会被拒绝）
WRITE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)

# 修改类写入：非破坏，但依赖当前状态 → 非幂等（不承诺可安全重试）
WRITE_MUTATING = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
)

# 删除类写入：破坏性、非幂等
WRITE_DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
)
