from .base import Base
from .product import Product, ProductPrice


# 父实体可见性注册表：无自身归属列（data_scope/owner）的子表 → (父实体, 子表外键列名)。
# 查询子表时按"父实体可见"过滤子行（孤儿行豁免），由
# QueryHandler._parent_visibility_where 消费；新增同类子表只需登记一行。
PARENT_ENTITY_MAP: dict[type[Base], tuple[type[Base], str]] = {
    ProductPrice: (Product, "product_id"),
}


__all__ = ["PARENT_ENTITY_MAP", "Base", "Product", "ProductPrice"]
