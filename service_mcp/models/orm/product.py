__all__ = ["Product", "ProductPrice"]

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DECIMAL,
    Boolean,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_mcp.models.orm.base import Base, EnumInt
from service_mcp.utils.enums import AbnormalType, ProductCategory


class Product(Base):
    """商品主数据（示例实体：唯一业务编码 + 软删除 + 异常标记 + 占位自动创建）。

    字段与同族 backend/frontend 的 demo 商品契约对齐：对外业务键是 `code`，
    不是主键；`category` 取值与 backend `ProductCategoryChoices` 同口径。
    """

    __tablename__ = "product"

    code: Mapped[str] = mapped_column(String(50), unique=True, comment="业务编码")
    name: Mapped[str] = mapped_column(String(200), comment="商品名称")
    category: Mapped[ProductCategory | int] = mapped_column(
        EnumInt(ProductCategory), default=ProductCategory.GOODS, comment="品类"
    )
    price: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2), default=Decimal("0.00"), comment="售价"
    )
    stock: Mapped[int] = mapped_column(Integer, default=0, comment="库存")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否上架")
    remark: Mapped[str | None] = mapped_column(Text, default=None, comment="备注")
    abnormal: Mapped[AbnormalType | None] = mapped_column(
        EnumInt(AbnormalType), default=None, comment="异常标记"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="软删除标记")

    # 关系
    prices: Mapped[list["ProductPrice"]] = relationship("ProductPrice", back_populates="product")

    __table_args__ = (
        Index("idx_product_name", "name"),  # 按名称搜索（如 LIKE）
        Index("idx_product_is_deleted", "is_deleted"),
        Index("idx_product_category", "category"),
        Index("idx_product_is_active", "is_active"),
    )


class ProductPrice(Base):
    """商品价格快照（示例实体：复合唯一键 + 版本列 + 异常标记 + FK code 解析）。

    对外输入用 `code`（Product.code）定位商品，handler 解析为内部 `product_id`；
    `product_id` 不在请求/响应中对外暴露为业务键。
    """

    __tablename__ = "product_price"

    product_id: Mapped[int | None] = mapped_column(Integer, comment="商品ID，关联product表的ID")
    price_date: Mapped[date] = mapped_column(Date, comment="价格日期")
    price: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), comment="售价")
    version: Mapped[int] = mapped_column(Integer, default=0, comment="版本号")
    abnormal: Mapped[AbnormalType | None] = mapped_column(
        EnumInt(AbnormalType), default=None, comment="异常标记"
    )

    # 关系
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="prices")

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "price_date",
            "version",
            name="uq_product_price_date_version",
        ),
        ForeignKeyConstraint(["product_id"], ["product.id"]),
        Index("idx_price_date", "price_date"),  # 按日期排序/筛选
    )
