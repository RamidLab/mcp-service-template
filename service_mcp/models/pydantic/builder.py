from __future__ import annotations


__all__ = ["create_filter_class", "create_search_class"]

from datetime import date, datetime
from types import UnionType
from typing import (
    Any,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import Field, create_model
from sqlalchemy import Boolean, ColumnElement, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import InstrumentedAttribute, Mapped
from sqlalchemy.sql.sqltypes import Enum as SQLEnum

from service_mcp.models.orm import Base
from service_mcp.models.pydantic import (
    BaseFilter,
    BaseSearchByFields,
    BaseSearchByKeyword,
    FilterField,
    SearchField,
)
from service_mcp.models.pydantic.generate import register_pyi_class
from service_mcp.utils.log import get_logger


logger = get_logger(__name__)


def _extract_py_type_from_annotation(raw_type: type, col_type: type | None = None) -> type | None:
    """
    解析注解并可选地校验枚举兼容性。
    如果 col_type 不为 None，且提取出的类型是枚举，则做兼容性检查，
    不兼容时返回常规 Python 类型。

    Args:
        raw_type: 原始类型注解
        col_type: SQLAlchemy 列对象的类型注解，用于校验枚举兼容性

    Returns:
        解析后的 Python 类型，或 None 表示无法解析
    """
    origin = get_origin(raw_type)
    args = get_args(raw_type)

    # 剥离 Mapped / Optional
    if origin is Mapped and args:
        return _extract_py_type_from_annotation(args[0], col_type)
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _extract_py_type_from_annotation(non_none[0], col_type)
        return None

    if not isinstance(raw_type, type):
        return None

    if col_type is not None and issubclass(raw_type, SQLEnum):
        if issubclass(raw_type, int) and isinstance(col_type, Integer):
            return raw_type
        if issubclass(raw_type, str) and isinstance(col_type, (String, Text)):
            return raw_type
        # 不兼容枚举 -> 不返回枚举，由外层继续走常规映射
        return None

    return raw_type


def _safe_column_python_type(col: InstrumentedAttribute) -> type:
    """
    安全获取列对应的 Python 类型。
        - 枚举返回枚举类
        - 常见 SQLAlchemy 类型做显式映射
        - 失败返回 Any

    Args:
        col: SQLAlchemy 列对象

    Returns:
        Python 类型
    """
    col_type = getattr(col, "type", None)
    if col_type is not None:
        try:
            if isinstance(col_type, SQLEnum):
                enum_class = getattr(col_type, "enum_class", None)
                if isinstance(enum_class, type):
                    return enum_class
        except (AttributeError, NotImplementedError):
            pass

    # 尝试从模型类的类型注解中提取真实 Python 类型
    # noinspection PyBroadException
    try:
        model_cls = col.class_  # 获取声明该属性的模型类
        _annotations = get_type_hints(model_cls, include_extras=True)
        raw_type = _annotations.get(col.key, None)
        if raw_type is not None and isinstance(raw_type, type):
            extracted = _extract_py_type_from_annotation(raw_type)
            if extracted is not None and issubclass(extracted, SQLEnum):
                # 仅当提取的类型是 Integer/BigInteger/SmallInteger/String/Text + Enum 子类，且与列存储兼容时才返回
                return extracted
    except Exception:
        pass

    if col_type is not None:
        try:
            type_map = {
                Integer: int,
                String: str,
                Text: str,
                Date: date,
                DateTime: datetime,
                Boolean: bool,
            }
            for sa_type, py_type in type_map.items():
                if isinstance(col_type, sa_type):
                    return py_type

            py_type = getattr(col_type, "python_type", None)
            if isinstance(py_type, type):
                return py_type
        except (AttributeError, NotImplementedError):
            pass

    return Any


def _selected_model_columns(
    model: type[Base],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    *,
    text_only: bool = False,
) -> dict[str, InstrumentedAttribute]:
    """
    从模型中选择列。

    Args:
        - model: 模型类
        - include: 白名单列名（可选）
        - exclude: 黑名单列名（可选）
        - text_only: 是否仅保留 String/Text 列（默认 False）
    Returns:
        - 选中的列名到 InstrumentedAttribute 映射
    """
    selected: dict[str, InstrumentedAttribute] = {}
    table_columns = list(getattr(model.__table__, "columns", []))

    for col in table_columns:
        col_name = col.name

        if include is not None:
            if col_name not in include:
                continue
        else:
            if (col.primary_key and col.autoincrement) or (exclude and col_name in exclude):
                continue

        if text_only and not isinstance(col.type, (String, Text)):
            continue

        attr: InstrumentedAttribute | None = getattr(model, col_name, None)
        if attr is not None:
            selected[col_name] = attr

    return selected


def _check_field_conflicts(
    *,
    auto_names: set[str],
    column_mappings: dict[str, Any],
    extra_fields: dict[str, Any] | None = None,
    relation_field_names: set[str] | None = None,
    context: str = "Filter",
    suppress_warnings: bool = False,
) -> None:
    """
    统一冲突检测。

    Args:
        - auto_names: 自动选取的列名（来自模型）
        - column_mappings: 手动覆盖的列名（搜索/过滤共用）
        - extra_fields: 过滤器的额外字段名
        - date_range_generated: 日期区间自动生成的起止字段名
        - relation_field_names: 搜索类的关系字段名
        - suppress_warnings: 是否静默处理报错的冲突
    """
    cm_names = set(column_mappings.keys()) if column_mappings else set()
    ef_names = set(extra_fields.keys()) if extra_fields else set()
    rel_names = relation_field_names or set()

    # extra_fields 覆盖任何已有字段
    if extra_fields is not None:
        ef_conflict = ef_names & (auto_names | cm_names)
        if ef_conflict:
            raise ValueError(
                f"[{context}] extra_fields 不能与已有字段冲突: {ef_conflict}。"
                f"如需覆盖请使用 column_mappings。"
            )

    # 关闭警告
    if suppress_warnings:
        return

    # column_mappings 覆盖自动列
    overlap_cm_auto = cm_names & auto_names
    if overlap_cm_auto:
        logger.warning(
            f"[{context}] column_mappings 覆盖自动列: {overlap_cm_auto}，将以 column_mappings 类型为准。"
            f"可通过 suppress_warnings=True 关闭此警告。",
        )

    # column_mappings 覆盖 extra_fields (仅过滤类)
    if extra_fields is not None:
        overlap_cm_ef = cm_names & ef_names
        if overlap_cm_ef:
            logger.warning(
                f"[{context}] column_mappings 覆盖 extra_fields: {overlap_cm_ef}，以 column_mappings 为准。"
                f"可通过 suppress_warnings=True 关闭此警告。",
            )

    # 搜索类：关系字段与文本列重名
    if rel_names:
        rel_overlap = rel_names & (auto_names | cm_names)
        if rel_overlap:
            logger.warning(
                f"[{context}] 关系映射字段与已有搜索字段重名: {rel_overlap}，"
                f"该字段将作为附加条件参与搜索。可通过 suppress_warnings=True 关闭此警告。",
            )


def _bind_property_value(cls: type, name: str, value: Any) -> None:
    """
    给类绑定一个只读 property，避免可变默认值问题。

    Args:
        - cls: 类
        - name: 属性名
        - value: 属性值
    """
    setattr(cls, name, property(lambda self, v=value: v))


def _drop_abstract_methods(cls: type, *method_names: str) -> None:
    """
    移除指定方法名的抽象方法。

    Args:
        - cls: 类
        - method_names: 要移除的抽象方法名。
    """
    # noinspection SpellCheckingInspection
    attr = "__abstractmethods__"
    methods = frozenset(getattr(cls, attr, frozenset()))
    setattr(cls, attr, methods - frozenset(method_names))


def create_filter_class(
    model: type[Base],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    column_mappings: dict[
        str,
        InstrumentedAttribute
        | tuple[InstrumentedAttribute, type | UnionType]
        | tuple[InstrumentedAttribute, InstrumentedAttribute, type | UnionType],
    ]
    | None = None,
    extra_fields: dict[str, tuple[Any, Any]] | None = None,
    exclude_comparable_fields: list[str] | None = None,
    suppress_warnings: bool = False,
) -> type[BaseFilter]:
    """
    动态创建 Filter 子类（零类型警告、自动推断字段、全字段可选）。

    Args:
        model: ORM 模型类
        include: 白名单，只包含这些列（优先级高于exclude）
        exclude: 黑名单，排除这些列（include 为 None 时生效）
        column_mappings:
            本表/关联列的过滤映射。可选形式：
            - 本表列：InstrumentedAttribute 或 (InstrumentedAttribute, python_type)
            - 关联列：(relationship_attr, target_column, python_type)  三元组，自动生成 has()/any() 条件
            例: {"code": Product.product_code} 或 {"mgr": (ProductPrice.product.name, str)}
            或 {"product_name": (ProductPrice.product, Product.product_name, Optional[str])}
        extra_fields: 附加的非列业务字段，如排序控制等（不参与自动条件生成）
        exclude_comparable_fields: 需要保持普通类型（非 FilterField）的字段名列表
        suppress_warnings: 是否静默处理报错的冲突
    """
    class_name = f"{model.__name__}Filter"
    extra_fields = extra_fields or {}
    column_mappings = column_mappings or {}
    exclude_comparable = set(exclude_comparable_fields) if exclude_comparable_fields else set()

    selected_columns = _selected_model_columns(model, include=include, exclude=exclude)

    # 自动选取的列名（来自模型）
    auto_names = set(selected_columns.keys())

    _check_field_conflicts(
        auto_names=auto_names,
        column_mappings=column_mappings,
        extra_fields=extra_fields,
        context="Filter",
        suppress_warnings=suppress_warnings,
    )

    # 解析 column_mappings，区分普通列映射和关系列映射
    relation_filter_mappings: dict[
        str, tuple[InstrumentedAttribute, InstrumentedAttribute, type | UnionType]
    ] = {}
    for field_name, entry in list(column_mappings.items()):
        if isinstance(entry, tuple) and len(entry) == 3:
            # 三元组：关系映射
            rel_attr, target_col, py_type = entry
            relation_filter_mappings[field_name] = (rel_attr, target_col, py_type)
            # 如果此字段名与自动列重名，覆盖自动列（移除自动列）
            if field_name in selected_columns:
                del selected_columns[field_name]
        else:
            # 普通列映射
            if isinstance(entry, tuple):
                col, _ = entry
            else:
                col = entry
            selected_columns[field_name] = col

    # 构造字段定义
    fields_def: dict[str, tuple[type | UnionType, Any]] = {}
    filter_mappings: list[tuple[str, InstrumentedAttribute]] = []

    for field_name, col in selected_columns.items():
        if field_name in exclude_comparable:
            if field_name in column_mappings:
                entry = column_mappings[field_name]
                if isinstance(entry, tuple):
                    _, py_type = entry
                else:
                    py_type = _safe_column_python_type(col)
                    py_type = py_type | None
            else:
                py_type = _safe_column_python_type(col)
                py_type = py_type | None

            if not isinstance(py_type, type):
                py_type = Any

            comment = getattr(col, "comment", "") or ""
            fields_def[field_name] = (py_type, Field(default=None, description=comment))
        else:
            fields_def[field_name] = (cast("type", FilterField | None), Field(default=None))

        filter_mappings.append((field_name, col))

    # 为关系映射字段创建字段定义
    for field_name, (rel_attr, target_col, py_type) in relation_filter_mappings.items():
        if field_name in exclude_comparable:
            fields_def[field_name] = (py_type, Field(default=None))
        else:
            fields_def[field_name] = (cast("type", FilterField | None), Field(default=None))

    # 额外字段
    fields_def.update(extra_fields)

    # 创建动态类
    new_filter = create_model(class_name, __base__=BaseFilter, **fields_def)

    # 绑定只读属性，避免 mutable default warning
    _bind_property_value(new_filter, "_filter_mappings", tuple(filter_mappings))
    _bind_property_value(
        new_filter, "_relation_filter_mappings", tuple(relation_filter_mappings.items())
    )
    new_filter._model_class = staticmethod(lambda: model)

    def to_where(self) -> list[ColumnElement[bool]]:
        conditions = BaseFilter.to_where(self)
        for _field_name, (_rel_attr, _target_col, _py_type) in self._relation_filter_mappings:
            value = getattr(self, _field_name, None)
            if value is None:
                continue
            if isinstance(value, FilterField):
                cond = self._build_condition(_target_col, value)
            else:
                cond = _target_col == value
            if cond is not None:
                if _rel_attr.property.uselist:
                    conditions.append(_rel_attr.any(cond))
                else:
                    conditions.append(_rel_attr.has(cond))
        return conditions

    new_filter.to_where = to_where

    _drop_abstract_methods(new_filter, "_filter_mappings", "_model_class")

    register_pyi_class(class_name, BaseFilter, "filter", cls=new_filter)

    return new_filter


def create_search_class(
    model: type[Base],
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    column_mappings: dict[str, tuple[InstrumentedAttribute, type | UnionType]] | None = None,
    relation_mappings: dict[str, tuple[str, type[Base], str]] | None = None,
    suppress_warnings: bool = False,
) -> tuple[type[BaseSearchByKeyword], type[BaseSearchByFields]]:
    """
    根据 ORM 模型自动生成关键词搜索和字段搜索两个 Pydantic 类。

    Args:
        model: ORM 模型类
        include: 参与搜索的文本列白名单（若为 None 则自动包含所有 String/Text 列）
        exclude: 黑名单（include 为 None 时生效）
        column_mappings: 覆盖列映射表，例如 {'product_code': (Product.product_code, str)}
        relation_mappings: 跨表关系搜索，例如
            {'product_name': ('product', Product, 'product_name')}
        suppress_warnings: 是否静默处理报错的冲突
    """
    column_mappings = column_mappings or {}

    # 选择文本列
    search_columns = _selected_model_columns(
        model,
        include=include,
        exclude=exclude,
        text_only=True,
    )

    auto_names = set(search_columns.keys())

    _check_field_conflicts(
        auto_names=auto_names,
        column_mappings=column_mappings,
        relation_field_names=set(relation_mappings.keys()) if relation_mappings else None,
        context="Search",
        suppress_warnings=suppress_warnings,
    )

    # 覆盖列
    for name, (col, _) in column_mappings.items():
        search_columns[name] = col

    # 生成关键词搜索类
    class_name_kw = f"{model.__name__}SearchByKeyword"
    keyword_search_class = create_model(
        class_name_kw,
        __base__=BaseSearchByKeyword,
        keyword=(str, Field(..., description="搜索关键词")),
        match_mode=(Literal["exact", "fuzzy"], Field("fuzzy", description="匹配模式")),
    )

    def _or_conditions(self: BaseSearchByKeyword) -> list[Any]:
        fuzzy = self.match_mode == "fuzzy"
        expr = f"%{self.keyword}%" if fuzzy else self.keyword

        conditions: list[Any] = []
        for col_attr in search_columns.values():
            conditions.append(col_attr.ilike(expr) if fuzzy else col_attr == expr)

        if relation_mappings:
            for _, (rel_attr, target_model, target_col_name) in relation_mappings.items():
                target_col = getattr(target_model, target_col_name)
                rel = getattr(model, rel_attr)
                if rel.property.uselist:
                    cond = rel.any(target_col.ilike(expr)) if fuzzy else rel.any(target_col == expr)
                else:
                    cond = rel.has(target_col.ilike(expr)) if fuzzy else rel.has(target_col == expr)
                conditions.append(cond)
        return conditions

    keyword_search_class._or_conditions = _or_conditions
    _drop_abstract_methods(keyword_search_class, "_or_conditions")

    # 生成字段搜索类
    class_name_fs = f"{model.__name__}SearchByFields"
    fields_fs: dict[str, tuple[type | UnionType, Any]] = dict.fromkeys(
        search_columns, (cast("type", SearchField | None), None)
    )

    if relation_mappings:
        for field_name in relation_mappings:
            fields_fs[field_name] = (cast("type", SearchField | None), None)

    fields_fs["match_mode"] = (Literal["exact", "fuzzy"], Field("fuzzy"))
    fields_fs["logic"] = (Literal["and", "or"], Field("and"))

    field_search_class = create_model(class_name_fs, __base__=BaseSearchByFields, **fields_fs)

    _bind_property_value(
        field_search_class,
        "_column_mappings",
        [(name, getattr(model, name)) for name in search_columns],
    )

    if relation_mappings:
        _bind_property_value(
            field_search_class,
            "_relation_mappings",
            [
                (field_name, rel_attr, target_model, target_col_name)
                for field_name, (
                    rel_attr,
                    target_model,
                    target_col_name,
                ) in relation_mappings.items()
            ],
        )

    def _relation_cond(
        self: BaseSearchByFields,
        relation_attr: str,
        target_model: type[Base],
        target_col_name: str,
        field: SearchField,
    ) -> Any | None:
        if not field or field.value is None:
            return None
        rel = getattr(self._model_class(), relation_attr)
        target_col = getattr(target_model, target_col_name)
        condition = field.condition or self.match_mode
        fuzzy = condition == "fuzzy"
        if fuzzy:
            if rel.property.uselist:
                return rel.any(target_col.ilike(f"%{field.value}%"))
            return rel.has(target_col.ilike(f"%{field.value}%"))
        if rel.property.uselist:
            return rel.any(target_col == field.value)
        return rel.has(target_col == field.value)

    field_search_class._relation_cond = _relation_cond

    field_search_class._model_class = staticmethod(lambda: model)
    _drop_abstract_methods(field_search_class, "_column_mappings", "_model_class", "_relation_cond")

    register_pyi_class(class_name_kw, BaseSearchByKeyword, "search", cls=keyword_search_class)
    register_pyi_class(class_name_fs, BaseSearchByFields, "search", cls=field_search_class)

    return keyword_search_class, field_search_class
