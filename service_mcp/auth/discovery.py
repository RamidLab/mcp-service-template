"""权限码和实体元数据自动发现模块。

公开 get_all_permissions() 和 get_entity_metadata() 供外部系统调用。
"""

from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Integer

from service_mcp.models.orm.base import Base
from service_mcp.tools import (
    basic_tools,
    crud_tools,
    dict_tools,
    query_tools,
)
from service_mcp.utils.enums import AuthAction, AuthResource


_TOOL_MODULES = [
    query_tools,
    crud_tools,
    basic_tools,
    dict_tools,
]


def _make_name(resource: str, action: str) -> str:
    res = AuthResource.from_value(resource)
    act = AuthAction.from_value(action)
    res_name = getattr(res, "label", "未知")
    act_name = getattr(act, "label", "未定义")
    return f"{res_name}{act_name}"


def get_all_permissions() -> list[dict]:
    """返回 service-mcp 所有权限码清单。

    Returns:
        [{"code": "SM_010101", "name": "产品列表", "resource": "01", "action": "01"}, ...]
    """
    import inspect

    seen: dict[str, dict] = {}
    for mod in _TOOL_MODULES:
        for _name, obj in vars(mod).items():
            # inspect.isfunction 过滤 SQLAlchemy func 等动态生成器
            if inspect.isfunction(obj) and hasattr(obj, "_mcp_perm_code"):
                code = getattr(obj, "_mcp_perm_code", "")
                resource = getattr(obj, "_mcp_resource", "")
                action = getattr(obj, "_mcp_action", "")
                if code not in seen:
                    seen[code] = {
                        "code": code,
                        "name": _make_name(resource, action),
                        "resource": resource,
                        "action": action,
                    }
    return sorted(seen.values(), key=lambda p: p["code"])


# ── 实体元数据自动发现 ──


def _scan_entity_fields(model: type[Base]) -> list[dict[str, Any]]:
    """扫描 ORM 模型的所有字段，返回元数据列表。"""
    from enum import Enum as PyEnum
    from typing import get_args, get_origin

    fields = []
    model_annotations = getattr(model, "__annotations__", {})

    for col in model.__table__.columns.values():
        # 跳过主键和自增列
        if col.primary_key and col.autoincrement:
            continue

        field_key = col.name
        label = col.comment or field_key
        col_type = col.type

        # 推断类型
        field_type = "text"
        options = []

        # 检查枚举
        model_type = model_annotations.get(field_key)
        if model_type:
            origin = get_origin(model_type)
            if origin is not None:
                args = get_args(model_type)
                actual_type = args[0] if args else None
            else:
                actual_type = model_type

            # 处理 Optional
            if actual_type:
                union_origin = get_origin(actual_type)
                if union_origin is not None:
                    union_args = get_args(actual_type)
                    non_none = [a for a in union_args if a is not type(None)]
                    if non_none:
                        actual_type = non_none[0]

            if actual_type and isinstance(actual_type, type) and issubclass(actual_type, PyEnum):
                field_type = "select"
                # label 是项目枚举的动态属性，用 getattr 兜底
                options = [
                    {"value": m.value, "label": getattr(m, "label", str(m.value))}
                    for m in actual_type.__members__.values()
                ]

        if field_type == "text":
            if isinstance(col_type, (Date, DateTime)):
                field_type = "date_range"
            elif isinstance(col_type, Integer):
                field_type = "number"
            elif isinstance(col_type, Boolean):
                field_type = "boolean"

        # 语义域推断
        domain = None
        unit = None
        if field_type == "select":
            domain = "enum"
        elif field_type == "date_range":
            domain = "date"
        elif "金额" in label or "资本" in label:
            domain = "currency"
            unit = "万元"
        elif "比例" in label or "率" in label:
            domain = "rate"
            unit = "百分比"
        elif "状态" in label:
            domain = "status"

        fields.append(
            {
                "key": field_key,
                "label": label,
                "type": field_type,
                "domain": domain,
                "unit": unit,
                "nullable": col.nullable,
                "unique": col.unique or False,
            }
        )
        if options:
            fields[-1]["options"] = options

    return fields


def _scan_entity_relationships(model: type[Base]) -> list[dict[str, Any]]:
    """扫描 ORM 模型的关系，返回关系列表。"""
    relationships = []

    # 从 __table_args__ 提取外键约束
    table_args = getattr(model, "__table_args__", ())
    for arg in table_args:
        if hasattr(arg, "column_keys") and hasattr(arg, "referred_table"):
            # ForeignKeyConstraint
            source_fields = arg.column_keys
            target_table = (
                arg.referred_table.name
                if hasattr(arg.referred_table, "name")
                else str(arg.referred_table)
            )
            for sf in source_fields:
                relationships.append(
                    {
                        "field": sf,
                        "target_entity": target_table.replace("_", ""),
                        "target_field": "id",  # 默认
                        "type": "many_to_one",
                        "source": "fk_inferred",
                    }
                )

    # 从 relationship() 提取
    for rel_name, rel_prop in model.__mapper__.relationships.items():
        # Mapper.class_ 由 SQLAlchemy 动态赋值、无类型注解，经 Any 中间变量访问
        mapper: Any = rel_prop.mapper
        target_model: type = mapper.class_
        target_name = target_model.__name__.lower()
        rel_type = "one_to_many" if rel_prop.uselist else "many_to_one"

        # 检查是否已存在
        exists = any(r["target_entity"] == target_name for r in relationships)
        if not exists:
            relationships.append(
                {
                    "field": rel_name,
                    "target_entity": target_name,
                    "target_field": "id",
                    "type": rel_type,
                    "source": "relationship",
                }
            )

    return relationships


# ── 实体元数据缓存 ──

_ENTITY_METADATA_CACHE: dict[str, dict[str, Any]] | None = None


def get_entity_metadata() -> dict[str, dict[str, Any]]:
    """扫描所有 ORM 模型，返回实体元数据（使用缓存）。

    Returns:
        {
            "product": {
                "fields": [...],
                "relationships": [...],
                "enums": {...}
            },
            ...
        }
    """
    global _ENTITY_METADATA_CACHE
    if _ENTITY_METADATA_CACHE is not None:
        return _ENTITY_METADATA_CACHE

    from service_mcp.models.orm import Product, ProductPrice

    models = [
        Product,
        ProductPrice,
    ]

    result = {}
    for model in models:
        entity_type = model.__name__.lower()
        result[entity_type] = {
            "label": model.__doc__.strip().split("\n")[0] if model.__doc__ else entity_type,
            "fields": _scan_entity_fields(model),
            "relationships": _scan_entity_relationships(model),
        }

    _ENTITY_METADATA_CACHE = result
    return result
