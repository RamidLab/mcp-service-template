__all__ = [
    "ProductPriceSearchByFields",
    "ProductPriceSearchByKeyword",
    "ProductSearchByFields",
    "ProductSearchByKeyword",
]

from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.pydantic.builder import create_search_class


ProductSearchByKeyword, ProductSearchByFields = create_search_class(
    model=Product,
    include=[
        "code",
        "name",
        "remark",
    ],
)

ProductPriceSearchByKeyword, ProductPriceSearchByFields = create_search_class(
    model=ProductPrice,
    include=["price_date"],
    relation_mappings={
        "code": ("product", Product, "code"),
        "name": ("product", Product, "name"),
    },
)
