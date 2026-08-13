from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ColumnElement, and_, asc, desc, or_
from sqlalchemy.orm import InstrumentedAttribute

from service_mcp.models.orm import Base


T = TypeVar("T", bound=Base)

ScalarValue = int | float | str | bool | date | datetime
FilterValue = (
    ScalarValue
    | list[ScalarValue]  # in 操作符的值
    | tuple[ScalarValue | None, ScalarValue | None]  # between 操作符
)


class FilterField(BaseModel):
    value: FilterValue | None = Field(default=None, title="搜索值")
    condition: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "like", "between"] = "eq"

    @model_validator(mode="before")
    @classmethod
    def coerce_plain_value(cls, data):
        if not isinstance(data, dict):
            return {"value": data, "condition": "eq"}
        return data


class BaseFilter(BaseModel, ABC):
    """过滤器基类，提供排序和日期区间辅助方法。

    动态子类由 create_filter_class 生成并注入 _filter_mappings/_model_class 实现，
    因此这两个方法提供默认实现（非抽象），静态子类无需重复实现。
    """

    @property
    def _filter_mappings(self) -> list[tuple[str, InstrumentedAttribute]]:
        """返回 [(字段名, 对应模型列)] 列表，用于等值筛选"""
        raise NotImplementedError("由 create_filter_class 动态注入")

    @staticmethod
    def _model_class() -> type[T]:
        """返回过滤器对应的 ORM 模型类"""
        raise NotImplementedError("由 create_filter_class 动态注入")

    @staticmethod
    def _build_condition(
        col: InstrumentedAttribute, value: FilterField | None
    ) -> ColumnElement[bool] | None:
        """统一构造 SQL 条件，支持普通值和 FilterField"""
        if value is None:
            return None
        if not isinstance(value, FilterField):
            # 普通值 → 等值（向后兼容）
            return col == value
        # FilterField 对象
        op = value.condition
        val = value.value
        if op == "eq":
            return col == val
        if op == "ne":
            return col != val
        if op == "gt":
            return col > val
        if op == "gte":
            return col >= val
        if op == "lt":
            return col < val
        if op == "lte":
            return col <= val
        if op == "in":
            return col.in_(val if isinstance(val, (list, tuple)) else [val])
        if op == "like":
            # like 只对标量有意义；isinstance 收窄类型，避免联合中的 None/tuple 干扰
            if not isinstance(val, (str, int, float)):
                return None
            return col.like(f"%{val}%")
        if op == "between":
            if isinstance(val, (list, tuple)) and len(val) == 2:
                start, end = val
                if start is not None and end is not None:
                    return col.between(start, end)
                if start is not None:
                    return col >= start
                if end is not None:
                    return col <= end
                return None
            raise ValueError("between 的 value 必须是 (start, end) 二元组")
        raise ValueError(f"不支持的运算符: {op}")

    def to_order_by(self) -> list[ColumnElement[Any]]:
        """
        转换为 SQLAlchemy order by 条件列表
        子类可重写排序，默认调用 _build_order_by(self, model, self.sort_by)

        Returns:
            SQLAlchemy order by 条件列表
        """
        field_name: str | None = getattr(self, "sort_by", None)
        order = getattr(self, "sort_order", "asc")
        if field_name is None:
            return []
        if order not in ["asc", "desc"]:
            raise ValueError(f"无效的排序方向: {order}")
        direction = desc if order == "desc" else asc
        model = self._model_class()
        try:
            col = model.__table__.c[field_name]
        except KeyError:
            raise ValueError(f"无效的排序字段: {field_name}")
        return [direction(col)]

    def to_where(self) -> list[ColumnElement[bool]]:
        """
        转换为 SQLAlchemy where 条件列表
        子类实现具体的条件生成

        Returns:
            SQLAlchemy where 条件列表
        """
        conditions: list[ColumnElement[bool]] = []
        for field_name, col in self._filter_mappings:
            value = getattr(self, field_name, None)
            cond = self._build_condition(col, value)
            if cond is not None:
                conditions.append(cond)
        return conditions


class BaseSearchByKeyword(BaseModel, ABC):
    keyword: str = Field(..., description="搜索关键词")
    match_mode: Literal["exact", "fuzzy"] = Field("fuzzy", description="匹配模式")

    @abstractmethod
    def _or_conditions(self) -> list[ColumnElement[bool]]:
        """
        转换为 SQLAlchemy where 条件列表
        子类实现：返回需要 OR 搜索的条件列表

        Returns:
            SQLAlchemy where 条件列表
        """
        ...

    def to_where(self) -> list[ColumnElement[bool]]:
        return [or_(*self._or_conditions())]


class SearchField(BaseModel):
    """
    单个搜索字段，可以是纯字符串（默认模糊匹配）或包含匹配模式的对象。

    示例：
        纯字符串： "XXX" -> 模糊匹配
        对象：    {"value": "001", "mode": "exact"}  -> 精确匹配
    """

    value: str | None = Field(default=None, title="搜索值")
    condition: Literal["exact", "fuzzy"] | None = Field(
        default=None, title="匹配模式", description="exact=精确，fuzzy=模糊"
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_string_to_value(cls, data) -> dict[str, str | None] | str:
        """
        如果传入的是普通字符串，自动转换为 {'value': data, 'mode': None}
        这样后续会继承全局 match_mode（默认模糊）。
        """
        if isinstance(data, str):
            return {"value": data, "condition": None}
        return data


class SearchGroup(BaseModel):
    """搜索条件组 — 支持组内 AND/OR 逻辑"""

    conditions: dict[str, SearchField | None] = Field(
        default_factory=dict, description="组内字段条件"
    )
    logic: Literal["and", "or"] = Field("and", description="组内条件组合方式")


class BaseSearchByFields(BaseModel, ABC):
    """
    高级字段搜索抽象基类
    子类只需定义 `_field_mappings`（列字段）和可选的 `_relation_mappings`（关系字段）
    """

    match_mode: Literal["exact", "fuzzy"] = Field(
        "fuzzy", description="全局匹配模式（字段级可覆盖）"
    )
    logic: Literal["and", "or"] = Field("and", description="多条件组合方式")

    # 新增: 分组条件支持
    groups: list[SearchGroup] | None = Field(
        default=None, description="嵌套分组条件（优先级高于 logic）"
    )
    group_logic: list[Literal["and", "or"]] | None = Field(default=None, description="组间连接符")

    @property
    @abstractmethod
    def _column_mappings(self) -> list[tuple[str, InstrumentedAttribute]]:
        """返回 [(字段名, 模型列)] 列表，用于普通列搜索"""
        ...

    @property
    def _relation_mappings(self) -> list[tuple[str, str, type[T], str]]:
        """
        返回 [(字段名, 关系属性名, 目标模型, 目标列名)] 列表
        默认空列表，子类按需重写
        """
        return []

    def _like_or_eq(
        self, column: InstrumentedAttribute, field: SearchField
    ) -> ColumnElement[bool] | None:
        """
        根据匹配模式返回 SQLAlchemy 条件表达式

        Args:
            column: SQLAlchemy 列对象
            field: 搜索字段

        Returns:
            SQLAlchemy 条件表达式
        """
        if not field or field.value is None:
            return None
        mode = field.condition or self.match_mode
        return column.ilike(f"%{field.value}%") if mode == "fuzzy" else column == field.value

    def _relation_cond(
        self, relation_attr: str, target_model: Any, target_col_name: str, field: SearchField
    ) -> ColumnElement[bool] | None:
        """
        根据匹配模式返回 SQLAlchemy 条件表达式

        Args:
            relation_attr: 关系属性名
            target_model: 目标模型类
            target_col_name: 目标列名
            field: 搜索字段

        Returns:
            SQLAlchemy 条件表达式
        """
        if not field or field.value is None:
            return None
        target_col = getattr(target_model, target_col_name)
        rel = getattr(self._model_class(), relation_attr)
        mode = field.condition or self.match_mode
        if mode == "fuzzy":
            return rel.has(target_col.ilike(f"%{field.value}%"))
        return rel.has(target_col == field.value)

    @staticmethod
    @abstractmethod
    def _model_class() -> type[T]:
        """返回搜索的目标模型类"""
        ...

    def to_where(self) -> list[ColumnElement[bool]]:
        """转换为 SQLAlchemy where 条件列表，支持分组嵌套"""
        # 如果有分组条件，优先使用分组逻辑
        if self.groups:
            return self._build_grouped_conditions()
        return self._build_flat_conditions()

    def _build_flat_conditions(self) -> list[ColumnElement[bool]]:
        """构建平铺条件（原有逻辑）"""
        conditions: list[ColumnElement[bool]] = []

        # 普通列字段
        for field_name, col in self._column_mappings:
            field = getattr(self, field_name, SearchField())
            cond = self._like_or_eq(col, field)
            if cond is not None:
                conditions.append(cond)

        # 关系字段
        for field_name, rel_attr, target_model, target_col_name in self._relation_mappings:
            field = getattr(self, field_name, SearchField())
            cond = self._relation_cond(rel_attr, target_model, target_col_name, field)
            if cond is not None:
                conditions.append(cond)

        if self.logic == "or" and conditions:
            return [or_(*conditions)]
        return conditions

    def _build_grouped_conditions(self) -> list[ColumnElement[bool]]:
        """构建分组嵌套条件"""
        group_conditions: list[ColumnElement[bool]] = []

        for group in self.groups or []:
            inner_conditions = self._build_group_inner_conditions(group)
            if inner_conditions:
                if group.logic == "or":
                    group_conditions.append(or_(*inner_conditions))
                else:
                    group_conditions.append(and_(*inner_conditions))

        if not group_conditions:
            return []
        if len(group_conditions) == 1:
            return group_conditions

        # 用组间逻辑组合
        result = group_conditions[0]
        for i, logic in enumerate(self.group_logic or []):
            if i + 1 < len(group_conditions):
                if logic == "and":
                    result = and_(result, group_conditions[i + 1])
                else:
                    result = or_(result, group_conditions[i + 1])

        return [result]

    def _build_group_inner_conditions(self, group: SearchGroup) -> list[ColumnElement[bool]]:
        """构建单个组内的条件"""
        conditions: list[ColumnElement[bool]] = []

        # 构建字段名到列/关系的映射
        col_map = dict(self._column_mappings)
        rel_map = {item[0]: item[1:] for item in self._relation_mappings}

        for field_name, field in group.conditions.items():
            if field is None or field.value is None:
                continue

            if field_name in col_map:
                cond = self._like_or_eq(col_map[field_name], field)
                if cond is not None:
                    conditions.append(cond)
            elif field_name in rel_map:
                rel_attr, target_model, target_col_name = rel_map[field_name]
                cond = self._relation_cond(rel_attr, target_model, target_col_name, field)
                if cond is not None:
                    conditions.append(cond)

        return conditions


class BaseDeleteModel(BaseModel):
    """所有删除 Pydantic 模型的基类，提供 record_id 公共字段和通用字段清理。

    子类应定义具体的定位字段（编码、名称等）并通过 model_validator
    实现 _validate_delete_lookup 校验至少提供一个定位字段。
    """

    record_id: int | None = Field(default=None, description="记录ID")

    @classmethod
    def _strip_lookup(cls, v: str | None) -> str | None:
        """通用的定位字段清理：去除首尾空白，空白字符串转为 None。"""
        if v is None:
            return v
        return v.strip() or None


__all__ = [
    "BaseDeleteModel",
    "BaseFilter",
    "BaseSearchByFields",
    "BaseSearchByKeyword",
    "FilterField",
    "SearchField",
    "SearchGroup",
]
