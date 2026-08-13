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
        "product_code",
        "product_name",
        "product_short_name",
    ],
)

ProductPriceSearchByKeyword, ProductPriceSearchByFields = create_search_class(
    model=ProductPrice,
    include=["price_date"],
    relation_mappings={
        "product_code": ("product", Product, "product_code"),
        "product_name": ("product", Product, "product_name"),
    },
)
