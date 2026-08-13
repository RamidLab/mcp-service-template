import random
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import pytest
from faker import Faker
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    insert,
    select,
)

from service_mcp.db.core import DBManager
from service_mcp.models.orm import Base


fake = Faker("zh_CN")

TYPE_FAKER = {
    Integer: lambda: fake.random_int(min=1, max=9999),
    SmallInteger: lambda: fake.random_int(min=1, max=1000),
    BigInteger: lambda: fake.random_int(min=1, max=10**6),
    Float: lambda: round(random.uniform(0.01, 100.0), 2),
    Numeric: lambda: round(random.uniform(0.01, 100.0), 2),
    String: fake.word,
    Text: fake.sentence,
    Boolean: fake.boolean,
    Date: fake.date_object,
    DateTime: fake.date_time,
}


def _gen_value(col) -> int | float | str | bool | date | datetime:
    """
    根据列类型生成随机值

    Args:
        col: SQLAlchemy Column 对象

    Returns:
        随机值
    """
    # EnumInt 等 TypeDecorator：枚举列从合法成员值中随机取，避免读回时非法枚举报错
    enum_cls: type[Enum] | None = getattr(col.type, "enum_cls", None)
    if enum_cls is not None:
        members = list(enum_cls.__members__.values())
        return random.choice(members).value
    for col_type, gen in TYPE_FAKER.items():
        if isinstance(col.type, col_type):
            return gen()
    return "default"


def assert_row_matches(updated: dict[str, Any], new_data: dict[str, Any]) -> None:
    """比较更新后的行与期望数据（处理 Decimal 与日期/时间的比较差异）。"""
    for k, v in new_data.items():
        actual = updated[k]
        if isinstance(actual, Decimal):
            actual = float(actual)
        if isinstance(v, (date, datetime)):
            assert str(actual) == str(v), f"列 {k} 的值不匹配: {actual} != {v}"
        else:
            assert actual == pytest.approx(v), f"列 {k} 的值不匹配: {actual} != {v}"


def generate_fake_data(table_name: str) -> dict[str, Any]:
    """
    生成随机数据，不返回外键依赖

    Args:
        table_name: 表名

    Returns:
        包含随机数据的字典
    """
    table = Base.metadata.tables[table_name]
    data = {}
    for col in table.columns:
        if col.primary_key and col.autoincrement:
            continue
        if col.foreign_keys:
            if not col.nullable:
                data[col.name] = 1
            continue
        value = _gen_value(col)
        if isinstance(col.type, (String, Text)):
            max_len = getattr(col.type, "length", None)
            if isinstance(max_len, int) and isinstance(value, str) and max_len < len(value):
                value = value[:max_len]
        data[col.name] = value
    return data


async def ensure_dependencies(
    db: DBManager, table_name: str, visited: set | None = None
) -> dict[str, Any]:
    """
    确保外键依赖的表数据已存在

    Args:
        db: 数据库管理器
        table_name: 表名
        visited: 已访问表名集合，默认 None

    Returns:
        包含外键依赖的字典
    """
    if visited is None:
        visited = set()
    if table_name in visited:
        return {}
    visited.add(table_name)

    table = Base.metadata.tables[table_name]
    fk_vals = {}
    for fk in table.foreign_key_constraints:
        parent = fk.referred_table
        if parent.name == table_name:
            continue
        await ensure_dependencies(db, parent.name, visited)

        pk_col = next(iter(parent.primary_key))
        row = await db.fetch_one(select(parent.c[pk_col.name]).limit(1))
        if row is None:
            p_data = generate_fake_data(parent.name)
            p_data.update(await ensure_dependencies(db, parent.name, visited))
            await db.execute(insert(parent).values(**p_data))
            row = await db.fetch_one(select(parent.c[pk_col.name]).limit(1))
            assert row is not None, f"无法为父表 {parent.name} 插入依赖数据"
        for local_col in fk.columns:
            fk_vals[local_col.name] = row[pk_col.name]
    return fk_vals


async def build_row_data(db: DBManager, table_name: str) -> dict[str, Any]:
    """
    构建包含外键依赖的随机数据

    Args:
        db: 数据库管理器
        table_name: 表名

    Returns:
        包含随机数据的字典
    """
    data = generate_fake_data(table_name)
    data.update(await ensure_dependencies(db, table_name))
    return data


@pytest.fixture(params=["insert", "update", "delete", "fetch"])
async def crud_operation(request) -> str:
    """CRUD 操作 fixture，用于测试数据库操作"""
    return request.param


@pytest.fixture(
    params=[
        "product",
        "product_price",
    ]
)
async def table_name(request):
    """表名 fixture，用于测试数据库操作"""
    return request.param


async def insert_row(db: DBManager, table_name: str, data: dict[str, Any]):
    """插入一条数据到指定表"""
    table = Base.metadata.tables[table_name]
    await db.execute(insert(table).values(**data))


class TestDBManager:
    """测试真实数据库连接管理器"""

    @pytest.mark.asyncio
    async def test_connect(self, db_manager: DBManager):
        """测试数据库连接"""
        assert db_manager._engine is not None  # noqa
        assert db_manager._session_factory is not None  # noqa
        assert await db_manager.health_check() is True

    @pytest.mark.asyncio
    async def test_drop_all(self, db_manager: DBManager):
        """测试删除所有表"""
        await db_manager.drop_all()
        _tables = await db_manager.get_all_tables()
        assert _tables == []

    @pytest.mark.asyncio
    async def test_execute(self, db_manager: DBManager, crud_operation: str):
        """测试执行 CRUD 操作"""
        table = Base.metadata.tables["product"]
        pk_col = next(iter(table.primary_key))

        data = await build_row_data(db_manager, "product")
        await insert_row(db_manager, "product", data)

        if crud_operation == "insert":
            # 验证刚才插入的行存在
            row = await db_manager.fetch_one(select(table).limit(1))
            assert row is not None
            assert row["product_name"] == data["product_name"]

        elif crud_operation == "update":
            row = await db_manager.fetch_one(select(table).limit(1))
            assert row is not None, f"表 {table.name} 没有数据"
            pk_val = row[pk_col.name]
            new_data = generate_fake_data("product")
            await db_manager.execute(table.update().where(pk_col == pk_val).values(**new_data))
            updated = await db_manager.fetch_one(select(table).where(pk_col == pk_val))
            assert updated is not None
            assert_row_matches(updated, new_data)

        elif crud_operation == "delete":
            row = await db_manager.fetch_one(select(table).limit(1))
            assert row is not None, f"表 {table.name} 没有数据"
            pk_val = row[pk_col.name]
            await db_manager.execute(table.delete().where(pk_col == pk_val))
            deleted = await db_manager.fetch_one(select(table).where(pk_col == pk_val))
            assert deleted is None

        elif crud_operation == "fetch":
            row = await db_manager.fetch_one(select(table).limit(1))
            assert row is not None, f"表 {table.name} 没有数据"
            pk_val = row[pk_col.name]
            row = await db_manager.fetch_one(select(table).where(pk_col == pk_val))
            assert row is not None
            assert row[pk_col.name] == pk_val


class TestTable:
    @staticmethod
    async def _insert_and_get_pk(db_manager: DBManager, table_name: str):
        """插入一条假数据并返回 (table, pk_col, pk_val)"""
        table = Base.metadata.tables[table_name]
        data = await build_row_data(db_manager, table_name)
        await insert_row(db_manager, table_name, data)
        pk_col = next(iter(table.primary_key))
        row = await db_manager.fetch_one(select(table).limit(1))
        assert row is not None, f"表 {table_name} 插入数据失败"
        pk_val = row[pk_col.name]
        return table, pk_col, pk_val

    @staticmethod
    async def _assert_count(db_manager: DBManager, table, expected: int):
        """断言表中行数等于预期值"""
        result = await db_manager.execute(select(func.count()).select_from(table))
        assert result.scalar() == expected

    @pytest.mark.asyncio
    async def test_insert(self, db_manager: DBManager, table_name: str):
        """测试插入数据"""
        table, _, _ = await self._insert_and_get_pk(db_manager, table_name)
        await self._assert_count(db_manager, table, 1)

    @pytest.mark.asyncio
    async def test_update(self, db_manager: DBManager, table_name: str):
        """测试更新数据"""
        table, pk_col, pk_val = await self._insert_and_get_pk(db_manager, table_name)
        new_data = generate_fake_data(table_name)
        await db_manager.execute(table.update().where(pk_col == pk_val).values(**new_data))
        updated = await db_manager.fetch_one(select(table).where(pk_col == pk_val))
        assert updated is not None, f"更新后的 {table_name} 行不存在"
        assert_row_matches(updated, new_data)

    @pytest.mark.asyncio
    async def test_delete(self, db_manager: DBManager, table_name: str):
        """测试删除数据"""
        table, pk_col, pk_val = await self._insert_and_get_pk(db_manager, table_name)
        await db_manager.execute(table.delete().where(pk_col == pk_val))
        await self._assert_count(db_manager, table, 0)
