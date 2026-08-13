"""UpdateHandler 测试：record_id/自有编码定位、部分更新、唯一性冲突。"""

import pytest

from service_mcp.handlers.update_handlers import UpdateHandler
from service_mcp.models.orm import Product
from service_mcp.models.pydantic.product import ProductUpdate
from service_mcp.utils.enums import Errcode, ProductStatus, ProductType
from tests.conftest import HANDLER_DB_NAME, fetch_product, response_data


async def test_update_by_record_id(handler_db, seeded_product):
    """通过 record_id 更新。"""
    handler = UpdateHandler()
    data = ProductUpdate(product_name="改名产品", status=ProductStatus.Inactive)
    resp = await handler.handle(Product, data, seeded_product.id, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_product(handler_db, seeded_product.id)
    assert obj.product_name == "改名产品"
    assert obj.status is ProductStatus.Inactive


async def test_update_by_own_code(handler_db, seeded_product):
    """未传 record_id 时通过 product_code 定位。"""
    handler = UpdateHandler()
    data = ProductUpdate(product_code="P0001", product_name="按码定位改名")
    resp = await handler.handle(Product, data, None, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_product(handler_db, seeded_product.id)
    assert obj.product_name == "按码定位改名"


async def test_update_partial_none_ignored(handler_db, seeded_product):
    """None 字段不参与更新。"""
    handler = UpdateHandler()
    data = ProductUpdate(product_name="部分更新")
    resp = await handler.handle(Product, data, seeded_product.id, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_product(handler_db, seeded_product.id)
    # 未提供的字段保持原值
    assert obj.product_type is ProductType.Equity
    assert obj.launch_date is not None


async def test_update_no_fields(handler_db, seeded_product):
    """全部字段为 None 时返回"没有需要更新的字段"。"""
    handler = UpdateHandler()
    resp = await handler.handle(Product, ProductUpdate(), seeded_product.id, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    assert "没有需要更新的字段" in resp.message


async def test_update_code_conflict(handler_db, seeded_product):
    """product_code 改为已存在的编码 → 预校验抛 UniqueConflictError。"""
    await handler_db.insert(Product(product_code="P9998", product_name="另一产品"))
    handler = UpdateHandler()
    data = ProductUpdate(product_code="P9998")
    with pytest.raises(Exception, match="P9998"):
        await handler.handle(Product, data, seeded_product.id, HANDLER_DB_NAME)


async def test_update_not_found(handler_db):
    """定位不到记录时抛 ValueError。"""
    handler = UpdateHandler()
    with pytest.raises(ValueError, match="未找到"):
        await handler.handle(Product, ProductUpdate(product_name="x"), 99999, HANDLER_DB_NAME)


async def test_update_batch(handler_db, seeded_product):
    """批量更新。"""
    other = await handler_db.insert(Product(product_code="P0200", product_name="批量目标"))
    handler = UpdateHandler()
    resp = await handler.handle_batch(
        Product,
        [seeded_product.id, other.id],
        [ProductUpdate(status=ProductStatus.Inactive), ProductUpdate(status=ProductStatus.Active)],
        HANDLER_DB_NAME,
    )
    assert resp.code == Errcode.SUCCESS
    assert response_data(resp)["count"] == 2
