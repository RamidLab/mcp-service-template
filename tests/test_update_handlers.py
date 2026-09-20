"""UpdateHandler 测试：record_id/自有编码定位、部分更新、唯一性冲突。"""

from decimal import Decimal

import pytest

from service_mcp.handlers.update_handlers import UpdateHandler
from service_mcp.models.orm import Product
from service_mcp.models.pydantic.product import ProductUpdate
from service_mcp.utils.enums import Errcode, ProductCategory
from tests.conftest import HANDLER_DB_NAME, fetch_product, response_data


async def test_update_by_record_id(handler_db, seeded_product):
    """通过 record_id 更新。"""
    handler = UpdateHandler()
    data = ProductUpdate(name="改名商品", is_active=False)
    resp = await handler.handle(Product, data, seeded_product.id, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_product(handler_db, seeded_product.id)
    assert obj.name == "改名商品"
    assert obj.is_active is False


async def test_update_by_own_code(handler_db, seeded_product):
    """未传 record_id 时通过 code 定位。"""
    handler = UpdateHandler()
    data = ProductUpdate(code="P0001", name="按码定位改名")
    resp = await handler.handle(Product, data, None, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_product(handler_db, seeded_product.id)
    assert obj.name == "按码定位改名"


async def test_update_partial_none_ignored(handler_db, seeded_product):
    """None 字段不参与更新。"""
    handler = UpdateHandler()
    data = ProductUpdate(name="部分更新")
    resp = await handler.handle(Product, data, seeded_product.id, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_product(handler_db, seeded_product.id)
    # 未提供的字段保持原值
    assert obj.category is ProductCategory.GOODS
    assert obj.stock == 10
    assert obj.price == Decimal("99.00")


async def test_update_no_fields(handler_db, seeded_product):
    """全部字段为 None 时返回"没有需要更新的字段"。"""
    handler = UpdateHandler()
    resp = await handler.handle(Product, ProductUpdate(), seeded_product.id, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    assert "没有需要更新的字段" in resp.message


async def test_update_code_conflict(handler_db, seeded_product):
    """code 改为已存在的编码 → 预校验抛 UniqueConflictError。"""
    await handler_db.insert(Product(code="P9998", name="另一商品"))
    handler = UpdateHandler()
    data = ProductUpdate(code="P9998")
    with pytest.raises(Exception, match="P9998"):
        await handler.handle(Product, data, seeded_product.id, HANDLER_DB_NAME)


async def test_update_not_found(handler_db):
    """定位不到记录时抛 ValueError。"""
    handler = UpdateHandler()
    with pytest.raises(ValueError, match="未找到"):
        await handler.handle(Product, ProductUpdate(name="x"), 99999, HANDLER_DB_NAME)


async def test_update_batch(handler_db, seeded_product):
    """批量更新。"""
    other = await handler_db.insert(Product(code="P0200", name="批量目标"))
    handler = UpdateHandler()
    resp = await handler.handle_batch(
        Product,
        [seeded_product.id, other.id],
        [ProductUpdate(is_active=False), ProductUpdate(is_active=True)],
        HANDLER_DB_NAME,
    )
    assert resp.code == Errcode.SUCCESS
    assert response_data(resp)["count"] == 2
