"""Product/ProductPrice ORM 模型测试：表结构、约束、索引、枚举往返。"""

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import Table, select

from service_mcp.models.orm import Base, Product, ProductPrice
from service_mcp.utils.enums import ProductCategory


@pytest.mark.parametrize("table", ["product", "product_price"])
async def test_table_exists(db_manager, table):
    """两张示例表均已注册到 Base.metadata。"""
    assert table in Base.metadata.tables


async def test_product_columns_exist(db_manager):
    """product 表包含核心业务列与审计列（与 backend/frontend demo 契约对齐）。"""
    cols = {c.name for c in Product.__table__.columns.values()}
    assert {
        "id",
        "code",
        "name",
        "category",
        "price",
        "stock",
        "is_active",
        "remark",
        "abnormal",
        "is_deleted",
        "created_at",
        "updated_at",
    } <= cols


async def test_product_price_columns_exist(db_manager):
    """product_price 表包含复合唯一键相关列（教学模式字段，无金融衍生列）。"""
    cols = {c.name for c in ProductPrice.__table__.columns.values()}
    assert {
        "id",
        "product_id",
        "price_date",
        "price",
        "version",
        "abnormal",
    } <= cols
    # 金融风字段已删除
    assert not ({"acc_price", "daily_return_rate", "data_source", "unit_price"} & cols)


async def test_unique_product_code(db_manager):
    """code 唯一约束生效。"""
    await db_manager.insert(Product(code="P0001", name="甲"))
    with pytest.raises(Exception):
        await db_manager.insert(Product(code="P0001", name="乙"))


async def test_compound_unique_price(db_manager):
    """product_price 复合唯一键 (product_id, price_date, version) 生效。"""
    p = await db_manager.insert(Product(code="P0001", name="甲"))
    base = {
        "product_id": p.id,
        "price_date": date(2026, 6, 1),
        "price": Decimal("1.00"),
        "version": 0,
    }
    await db_manager.insert(ProductPrice(**base))
    with pytest.raises(Exception):
        await db_manager.insert(ProductPrice(**base))


async def test_foreign_key_price_to_product(db_manager):
    """product_price.product_id 外键约束引用 product.id。"""
    with pytest.raises(Exception):
        await db_manager.insert(
            ProductPrice(
                product_id=99999,
                price_date=date(2026, 6, 1),
                price=Decimal("1.00"),
                version=0,
            )
        )


async def test_indexes_exist(db_manager):
    """关键索引均已创建。"""
    product_table = cast(Table, Product.__table__)
    price_table = cast(Table, ProductPrice.__table__)
    product_indexes = {idx.name for idx in product_table.indexes}
    assert {"idx_product_name", "idx_product_is_deleted"} <= product_indexes
    price_indexes = {idx.name for idx in price_table.indexes}
    assert {"idx_price_date"} <= price_indexes


async def test_enum_int_roundtrip(db_manager):
    """EnumInt 列：写入枚举对象，读回还原为枚举成员。"""
    p = await db_manager.insert(
        Product(
            code="P0002",
            name="枚举测试",
            category=ProductCategory.SERVICE,
        )
    )
    async with db_manager.get_session() as session:
        row: Product | None = (
            (await session.execute(select(Product).where(Product.id == p.id))).scalars().first()
        )
    assert row is not None
    assert row.category is ProductCategory.SERVICE


async def test_soft_delete_flag_default(db_manager):
    """is_deleted 默认 False。"""
    p = await db_manager.insert(Product(code="P0003", name="软删测试"))
    async with db_manager.get_session() as session:
        row: Product | None = (
            (await session.execute(select(Product).where(Product.id == p.id))).scalars().first()
        )
    assert row is not None
    assert row.is_deleted is False
