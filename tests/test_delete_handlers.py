"""DeleteHandler 测试：多种定位方式、复合键删除、孤儿标记。"""

import pytest
from pydantic import ValidationError

from service_mcp.handlers.delete_handlers import DeleteHandler
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.pydantic.product import (
    ProductDelete,
    ProductPriceDelete,
)
from service_mcp.utils.enums import AbnormalType, Errcode
from tests.conftest import (
    HANDLER_DB_NAME,
    fetch_price,
    fetch_price_or_none,
    fetch_product_or_none,
)


async def test_delete_by_record_id(handler_db, seeded_product):
    handler = DeleteHandler()
    resp = await handler.handle(
        Product, ProductDelete(record_id=seeded_product.id), HANDLER_DB_NAME
    )
    assert resp.code == Errcode.SUCCESS
    assert await fetch_product_or_none(handler_db, seeded_product.id) is None


async def test_delete_by_code(handler_db, seeded_product):
    handler = DeleteHandler()
    resp = await handler.handle(Product, ProductDelete(product_code="P0001"), HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    assert await fetch_product_or_none(handler_db, seeded_product.id) is None


async def test_delete_by_name(handler_db, seeded_product):
    handler = DeleteHandler()
    resp = await handler.handle(Product, ProductDelete(product_name="测试产品"), HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    assert await fetch_product_or_none(handler_db, seeded_product.id) is None


async def test_delete_marks_orphans(handler_db, seeded_product, seeded_price):
    """删除产品后，其价格记录被标记 abnormal=Orphaned（数据保留）。"""
    handler = DeleteHandler()
    resp = await handler.handle(Product, ProductDelete(product_code="P0001"), HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    price = await fetch_price(handler_db, seeded_price.id)
    assert price.abnormal is AbnormalType.Orphaned


async def test_delete_price_by_compound_key(handler_db, seeded_product, seeded_price):
    """价格记录通过 product_code + price_date 复合键定位删除。"""
    handler = DeleteHandler()
    resp = await handler.handle(
        ProductPrice,
        ProductPriceDelete(product_code="P0001", price_date="2026-06-01"),
        HANDLER_DB_NAME,
    )
    assert resp.code == Errcode.SUCCESS
    assert await fetch_price_or_none(handler_db, seeded_price.id) is None


async def test_delete_price_missing_compound(handler_db, seeded_product):
    """复合键定位不到记录时抛 ValueError。"""
    handler = DeleteHandler()
    with pytest.raises(ValueError, match="价格记录"):
        await handler.handle(
            ProductPrice,
            ProductPriceDelete(product_code="P0001", price_date="2030-01-01"),
            HANDLER_DB_NAME,
        )


async def test_delete_validation_no_lookup(handler_db):
    """既无 record_id 也无定位字段时，Pydantic 校验直接报错。"""
    with pytest.raises(ValidationError):
        ProductDelete()
