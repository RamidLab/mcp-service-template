from sqlalchemy import ColumnElement
from typing import Any
from service_mcp.models.pydantic import BaseFilter


class ProductFilter(BaseFilter):
    def to_where(self) -> list[ColumnElement[bool]]: ...
    abnormal: Any = None
    created_at: Any = None
    created_by: Any = None
    data_source: Any = None
    keyword: Any = None
    launch_date: Any = None
    product_code: Any = None
    product_name: Any = None
    product_short_name: Any = None
    product_type: Any = None
    sort_by: Any = None
    sort_order: Any = None
    status: Any = None
    updated_at: Any = None

ProductPriceFilter: type[BaseFilter]
