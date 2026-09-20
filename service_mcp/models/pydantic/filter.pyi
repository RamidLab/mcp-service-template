from sqlalchemy import ColumnElement
from typing import Any
from service_mcp.models.pydantic import BaseFilter


class ProductFilter(BaseFilter):
    def to_where(self) -> list[ColumnElement[bool]]: ...
    abnormal: Any = None
    category: Any = None
    code: Any = None
    created_at: Any = None
    created_by: Any = None
    is_active: Any = None
    keyword: Any = None
    name: Any = None
    price: Any = None
    remark: Any = None
    sort_by: Any = None
    sort_order: Any = None
    stock: Any = None
    updated_at: Any = None

ProductPriceFilter: type[BaseFilter]
