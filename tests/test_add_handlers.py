"""AddHandler 测试：商品/价格新增、FK 解析、占位自动创建、价格冲突版本升级。"""

from datetime import date
from decimal import Decimal

from service_mcp.handlers.add_handlers import AddHandler
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.pydantic.product import (
    ProductCreate,
    ProductPriceCreate,
)
from service_mcp.utils.enums import AbnormalType, Errcode, ProductCategory
from tests.conftest import HANDLER_DB_NAME, fetch_price, fetch_product, response_data


async def test_add_product(handler_db, seeded_product):
    """基础添加：code + name 入库成功。"""
    handler = AddHandler()
    data = ProductCreate(
        code="P0002", name="新商品", category=ProductCategory.VIRTUAL, price=Decimal("12.30")
    )
    resp = await handler.handle(Product, data, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_product(handler_db, response_data(resp)["id"])
    assert obj.code == "P0002"
    assert obj.name == "新商品"
    assert obj.category is ProductCategory.VIRTUAL


async def test_add_product_duplicate_code(handler_db, seeded_product):
    """重复 code 返回 UNIQUE_CONFLICT（预校验拦截，带 code 值提示）。"""
    handler = AddHandler()
    data = ProductCreate(code="P0001", name="重复商品")
    resp = await handler.handle(Product, data, HANDLER_DB_NAME)
    assert resp.code == Errcode.UNIQUE_CONFLICT
    assert "P0001" in resp.message


async def test_add_price_resolves_fk(handler_db, seeded_product):
    """code 自动解析为 product_id，且 code 不入库为 ProductPrice 自身列。"""
    handler = AddHandler()
    data = ProductPriceCreate(
        code="P0001",
        price_date="2026-06-02",
        price=Decimal("20.00"),
    )
    resp = await handler.handle(ProductPrice, data, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_price(handler_db, response_data(resp)["id"])
    assert obj.product_id == seeded_product.id
    assert obj.price_date == date(2026, 6, 2)
    assert obj.version == 0
    assert obj.price == Decimal("20.00")


async def test_add_price_auto_placeholder(handler_db):
    """未知 code 自动创建占位 Product（abnormal=Placeholder），名称透传。"""
    handler = AddHandler()
    # model_validate 字典方式构造：name 是 extra="allow" 透传字段（用于占位创建），
    # 不走关键字参数构造，避免 PyCharm 的 PyArgumentList 检查误报
    data = ProductPriceCreate.model_validate(
        {
            "code": "P9999",
            "price_date": "2026-06-03",
            "price": Decimal("1.00"),
            "name": "未来商品",
        }
    )
    resp = await handler.handle(ProductPrice, data, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    price = await fetch_price(handler_db, response_data(resp)["id"])
    product_id = price.product_id
    assert product_id is not None
    product = await fetch_product(handler_db, product_id)
    assert product.code == "P9999"
    assert product.name == "未来商品"
    assert product.abnormal is AbnormalType.Placeholder


async def test_add_price_conflict_bumps_version(handler_db, seeded_price):
    """同日不同售价：自动 version+1 并标记 PriceConflict。"""
    handler = AddHandler()
    data = ProductPriceCreate(
        code="P0001",
        price_date="2026-06-01",
        price=Decimal("199.00"),  # 与 seeded_price 的 99.00 不同
    )
    resp = await handler.handle(ProductPrice, data, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    obj = await fetch_price(handler_db, response_data(resp)["id"])
    assert obj.version == 1
    assert obj.abnormal is AbnormalType.PriceConflict


async def test_add_price_identical_value_no_conflict(handler_db, seeded_price):
    """同日同售价：完全一致走 IntegrityError 返回 UNIQUE_CONFLICT，不升版本。"""
    handler = AddHandler()
    data = ProductPriceCreate(
        code="P0001",
        price_date="2026-06-01",
        price=Decimal("99.00"),
    )
    resp = await handler.handle(ProductPrice, data, HANDLER_DB_NAME)
    assert resp.code == Errcode.UNIQUE_CONFLICT


async def test_add_batch_partial_failure(handler_db, seeded_product, seeded_price):
    """批量添加价格：插入级冲突部分失败，不影响成功记录。"""
    handler = AddHandler()
    data_list = [
        ProductPriceCreate(
            code="P0001",
            price_date="2026-06-10",
            price=Decimal("10.00"),
        ),
        ProductPriceCreate(
            code="P0001",
            price_date="2026-06-01",  # 与 seeded_price 同日同价 → IntegrityError
            price=Decimal("99.00"),
        ),
    ]
    resp = await handler.handle_batch(ProductPrice, data_list, HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS
    data = response_data(resp)
    assert data["success_count"] == 1
    assert data["fail_count"] == 1
    assert data["failures"][0]["key"].get("price_date") is not None
