"""通用关联数据清除框架。

业务删除主记录时，按注册表清理关联数据。任何业务均可复用：

    register_cleanup(Product, CleanupRule(model=ProductPrice, where_builder=..., strategy=CASCADE))

清理规则声明三件事：
- 关联数据模型 + 关联条件构造器（where_builder，接收父 ORM 记录返回 where 条件列表）
- 清理策略（CASCADE 硬删 / ORPHAN 软标记 abnormal=Orphaned）
- 前置钩子（pre_delete，用于删除外部存储如 MinIO 附件，非 DB 事务）
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, update

from service_mcp.models.orm.base import Base
from service_mcp.utils.enums import AbnormalType


# 清理策略
CASCADE = "cascade"  # 硬删关联数据
ORPHAN = "orphan"  # 软标记 abnormal=Orphaned（数据保留供人工复核）


@dataclass
class CleanupRule:
    """关联数据清理规则。"""

    model: type[Base]
    where_builder: Callable[[Any], list]  # (父 ORM 记录) -> where 条件列表
    strategy: str = CASCADE
    pre_delete: Callable[[Any], Awaitable[None]] | None = None


_REGISTRY: dict[type[Base], list[CleanupRule]] = {}


def register_cleanup(parent_model: type[Base], rule: CleanupRule) -> None:
    """注册父模型删除时的关联数据清理规则。"""
    _REGISTRY.setdefault(parent_model, []).append(rule)


def build_cleanup_statements(parent_model: type[Base], parent_record: Any) -> list:
    """构造 DB 清理语句（delete/update），供调用方在删除父记录的事务内执行。"""
    statements: list = []
    for rule in _REGISTRY.get(parent_model, []):
        where = rule.where_builder(parent_record)
        if rule.strategy == CASCADE:
            statements.append(delete(rule.model).where(*where))
        elif rule.strategy == ORPHAN:
            statements.append(
                update(rule.model).where(*where).values(abnormal=AbnormalType.Orphaned)
            )
    return statements


async def run_pre_delete_hooks(parent_model: type[Base], parent_record: Any) -> None:
    """执行前置钩子（外部存储清理，如 MinIO 附件，不参与 DB 事务）。"""
    for rule in _REGISTRY.get(parent_model, []):
        if rule.pre_delete is not None:
            await rule.pre_delete(parent_record)
