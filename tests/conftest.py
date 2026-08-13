import os
from collections.abc import AsyncGenerator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import event, select

import service_mcp.config as config_module
from service_mcp.config import MCPSettings
from service_mcp.db.core import DBManager, _manager_cache  # noqa
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.utils.enums import ProductDataSource, ProductStatus, ProductType


HANDLER_DB_NAME = "handler_test"


def response_data(resp: UtilResponse) -> Any:
    """提取响应 data 并断言非 None（消除 Optional 访问警告）。

    返回 Any：data 可能是 PageData / dict / 其他结构，测试中按需访问。
    """
    data = resp.data
    assert data is not None
    return data


async def fetch_product_or_none(handler_db: DBManager, product_id: int) -> Product | None:
    """按 ID 查询产品，可能不存在（返回 None）。"""
    async with handler_db.get_session() as session:
        return (
            (await session.execute(select(Product).where(Product.id == product_id)))
            .scalars()
            .first()
        )


async def fetch_product(handler_db: DBManager, product_id: int) -> Product:
    """按 ID 查询产品，断言存在后返回（消除 Optional 成员访问警告）。"""
    obj = await fetch_product_or_none(handler_db, product_id)
    assert obj is not None
    return obj


async def fetch_price_or_none(handler_db: DBManager, price_id: int) -> ProductPrice | None:
    """按 ID 查询价格记录，可能不存在（返回 None）。"""
    async with handler_db.get_session() as session:
        return (
            (await session.execute(select(ProductPrice).where(ProductPrice.id == price_id)))
            .scalars()
            .first()
        )


async def fetch_price(handler_db: DBManager, price_id: int) -> ProductPrice:
    """按 ID 查询价格记录，断言存在后返回。"""
    obj = await fetch_price_or_none(handler_db, price_id)
    assert obj is not None
    return obj


@pytest.fixture(autouse=True)
def clean_globals():
    """每个测试前后重置全局 _settings 变量和清除环境变量影响"""
    # 保存原始值
    original_settings = config_module._settings  # noqa
    # 重置
    config_module._settings = None  # noqa
    yield
    config_module._settings = original_settings  # noqa
    # 清理可能的环境变量
    for key in list(os.environ.keys()):
        if key.startswith("MCP_"):
            del os.environ[key]


@pytest.fixture
def mock_config_path(tmp_path: Path, monkeypatch):
    """模拟配置文件路径为临时目录，并替换模块中的 _TOML_CONFIG"""
    fake_config = tmp_path / "config.test.toml"

    monkeypatch.setattr(config_module, "_TOML_CONFIG", fake_config)
    return fake_config


@pytest.fixture(autouse=True)
def patch_toml_file(mock_config_path, monkeypatch, request):
    """自动将所有测试中的 MCPSettings 的 toml_file 指向临时路径"""
    if request.node.get_closest_marker("no_auto_patch"):
        yield
    else:
        monkeypatch.setitem(MCPSettings.model_config, "toml_file", mock_config_path)
        yield


@pytest.fixture
def db_urls(tmp_path) -> dict[str, str]:
    return {
        "sqlite": "sqlite+aiosqlite:///:memory:",
        "sqlite_file": f"sqlite+aiosqlite:///{tmp_path}/test.db",
        "mysql": "mysql+asyncmy://root:root@127.0.0.1:3307/test",
        "postgresql": "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/test",
        "influxdb": "http://127.0.0.1:8087",
    }


@pytest.fixture(params=["sqlite", "sqlite_file", "mysql", "postgresql"])
async def db_manager(request, db_urls: dict[str, str]) -> AsyncGenerator["DBManager", None]:
    """数据库管理器 fixture，默认只使用 SQLite 内存数据库。"""
    db_name = request.param
    mgr = DBManager(db_urls[db_name])
    await mgr.connect()
    # SQLite 默认不强制外键约束，通过事件监听器在每个连接上开启
    url = db_urls[db_name]
    if url.startswith("sqlite"):

        @event.listens_for(mgr._engine.sync_engine, "connect")  # noqa
        def set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.close()

    await mgr.create_all()
    yield mgr
    await mgr.drop_all()
    await mgr.disconnect()


@pytest.fixture(autouse=True)
def clean_manager_cache():
    """每个测试前后清理全局 manager 缓存，确保隔离。"""
    _manager_cache.pop("db", None)  # noqa
    _manager_cache.pop("cache", None)  # noqa
    yield
    _manager_cache.pop("db", None)  # noqa
    _manager_cache.pop("cache", None)  # noqa


async def _create_handler_db() -> DBManager:
    mgr = DBManager("sqlite+aiosqlite:///:memory:")
    await mgr.connect()

    @event.listens_for(mgr._engine.sync_engine, "connect")  # noqa
    def _pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    await mgr.create_all()
    return mgr


@pytest.fixture
async def handler_db() -> AsyncGenerator[DBManager, None]:
    """为 handler 测试提供已注册的 SQLite 内存 DBManager。"""
    mgr = await _create_handler_db()
    _manager_cache.setdefault("db", {})[HANDLER_DB_NAME] = {"mgr": mgr, "db_type": "sqlite"}  # noqa
    yield mgr
    await mgr.drop_all()
    await mgr.disconnect()
    _manager_cache.pop("db", None)  # noqa


@pytest.fixture
async def seeded_product(handler_db: DBManager) -> Product:
    """预置一条 Product 记录。"""
    obj = Product(
        product_code="P0001",
        product_name="测试产品",
        product_short_name="测试",
        product_type=ProductType.Equity,
        status=ProductStatus.Active,
        launch_date=date(2024, 1, 1),
        data_source=ProductDataSource.ManualImport,
    )
    return await handler_db.insert(obj)


@pytest.fixture
async def seeded_price(handler_db: DBManager, seeded_product: Product) -> ProductPrice:
    """预置一条 ProductPrice 记录。"""
    obj = ProductPrice(
        product_id=seeded_product.id,
        price_date=date(2026, 6, 1),
        unit_price=1.2345,
        acc_price=2.3456,
        daily_return_rate=0.0123,
        data_source=ProductDataSource.ManualImport,
        version=0,
    )
    return await handler_db.insert(obj)
