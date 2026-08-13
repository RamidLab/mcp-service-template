__all__ = ["Product", "ProductPrice"]

from datetime import date
from typing import Optional

from sqlalchemy import (
    DECIMAL,
    Boolean,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_mcp.models.orm.base import Base, EnumInt
from service_mcp.utils.enums import AbnormalType, ProductDataSource, ProductStatus, ProductType


class Product(Base):
    """产品基本信息模型（示例实体：唯一业务编码 + 软删除 + 异常标记 + 占位自动创建）"""

    __tablename__ = "product"

    product_code: Mapped[str] = mapped_column(String(20), unique=True, comment="产品代码")
    product_name: Mapped[str] = mapped_column(String(200), comment="产品名称")
    product_short_name: Mapped[str | None] = mapped_column(String(100), comment="产品简称")
    product_type: Mapped[ProductType | None] = mapped_column(
        EnumInt(ProductType), default=ProductType.Unknown, comment="产品类型"
    )
    status: Mapped[ProductStatus | None] = mapped_column(
        EnumInt(ProductStatus), default=ProductStatus.Unknown, comment="产品状态"
    )
    launch_date: Mapped[date | None] = mapped_column(Date, comment="成立/上市日期")
    data_source: Mapped[ProductDataSource] = mapped_column(
        EnumInt(ProductDataSource), default=ProductDataSource.ManualImport, comment="数据来源"
    )
    abnormal: Mapped[AbnormalType | None] = mapped_column(
        EnumInt(AbnormalType), default=None, comment="异常标记"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="软删除标记")

    # 关系
    prices: Mapped[list["ProductPrice"]] = relationship("ProductPrice", back_populates="product")

    __table_args__ = (
        Index("idx_product_name", "product_name"),  # 按名称搜索（如 LIKE）
        Index("idx_product_status", "status"),  # 按状态筛选
        Index("idx_product_is_deleted", "is_deleted"),
    )


class ProductPrice(Base):
    """产品价格模型（示例实体：复合唯一键 + 版本列 + 异常标记 + FK code 解析）"""

    __tablename__ = "product_price"

    product_id: Mapped[int | None] = mapped_column(Integer, comment="产品ID，关联product表的ID")
    price_date: Mapped[date] = mapped_column(Date, comment="价格日期")
    unit_price: Mapped[float] = mapped_column(DECIMAL(12, 4), comment="单位价格")
    acc_price: Mapped[float | None] = mapped_column(DECIMAL(12, 4), comment="累计价格")
    daily_return_rate: Mapped[float | None] = mapped_column(DECIMAL(10, 4), comment="日涨跌幅")
    data_source: Mapped[ProductDataSource] = mapped_column(
        EnumInt(ProductDataSource), comment="数据来源"
    )
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
            "data_source",
            "version",
            name="uq_product_price_date_source_version",
        ),
        ForeignKeyConstraint(["product_id"], ["product.id"]),
        Index("idx_price_date", "price_date"),  # 按日期排序/筛选
    )
