"""数据库迁移脚本示例 —— 向已有 product 表补充新列。

本脚本是模板迁移示例：新增实体表或向已有表补列时，复制本文件修改 DDL 即可。
安全策略：用 SQLAlchemy Inspector 检测已存在的表和列，仅创建缺失项。
可重复执行（幂等）。支持 SQLite / PostgreSQL。

用法:
    uv run python scripts/migrate_example.py
    uv run python scripts/migrate_example.py --url sqlite+aiosqlite:///path/to/service_data.db
    uv run python scripts/migrate_example.py --url postgresql+asyncpg://user:pass@host/db
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, cast


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text

from service_mcp.db.core import DBManager


DEFAULT_URL = f"sqlite+aiosqlite:///{Path(__file__).resolve().parent.parent / 'service_data.db'}"


# ── DDL 模板 ──────────────────────────────────────────────
# 示例：老库中缺失 product 表时的兜底建表语句（正常情况由 ORM create_all() 创建）

CREATE_PRODUCT = """CREATE TABLE product (
    id INTEGER PRIMARY KEY,
    product_code VARCHAR(20) UNIQUE NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    product_short_name VARCHAR(100),
    product_type INTEGER DEFAULT 0,
    status INTEGER DEFAULT 0,
    launch_date DATE,
    data_source INTEGER DEFAULT 1,
    abnormal INTEGER,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)"""

# 需要补充到 product 表的新列（"schema 演进"场景：首次部署后加列）
PRODUCT_NEW_COLUMNS = [
    ("launch_date", "DATE"),
    ("is_deleted", "BOOLEAN DEFAULT FALSE"),
]


async def run_sql(mgr: DBManager, sql: str) -> None:
    async with mgr.session_factory() as session:
        await session.execute(text(sql))
        await session.commit()


class Migration:
    def __init__(self, mgr: DBManager, url: str):
        self.mgr = mgr
        self.url = url
        self.is_sqlite = "sqlite" in url

    # ── 检测方法 ──

    async def table_exists(self, table: str) -> bool:
        engine = self.mgr.engine
        async with engine.connect() as conn:

            def _check(sync_conn: Any) -> bool:
                inspector = cast(Any, inspect(sync_conn))
                return table in inspector.get_table_names()

            return await conn.run_sync(_check)

    async def column_exists(self, table: str, column: str) -> bool:
        engine = self.mgr.engine
        async with engine.connect() as conn:

            def _check(sync_conn: Any) -> bool:
                inspector = cast(Any, inspect(sync_conn))
                cols = inspector.get_columns(table)
                return any(c["name"] == column for c in cols)

            return await conn.run_sync(_check)

    async def get_existing_columns(self, table: str) -> list[str]:
        engine = self.mgr.engine
        async with engine.connect() as conn:

            def _check(sync_conn: Any) -> list[str]:
                inspector = cast(Any, inspect(sync_conn))
                return [c["name"] for c in inspector.get_columns(table)]

            return await conn.run_sync(_check)

    # ── DDL 生成 ──

    def alter_table_sql(self, table: str, col_name: str, col_def: str) -> str:
        """根据数据库类型生成 ALTER TABLE 语句"""
        if self.is_sqlite:
            return f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"
        return f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_def}"

    # ── 迁移逻辑 ──

    async def ensure_table(self, table: str, create_sql: str) -> None:
        if await self.table_exists(table):
            print(f"  [skip] {table} 已存在")
            return
        print(f"  [add]  创建表 {table}")
        await run_sql(self.mgr, create_sql)

    async def ensure_columns(self, table: str, columns: list[tuple[str, str]]) -> None:
        for col_name, col_def in columns:
            if await self.column_exists(table, col_name):
                print(f"  [skip] {table}.{col_name} 已存在")
            else:
                print(f"  [add]  {table}.{col_name}")
                sql = self.alter_table_sql(table, col_name, col_def)
                await run_sql(self.mgr, sql)

    async def ensure_base_columns(self, table: str) -> None:
        """确保表有 Base 模型的自动列（created_at, updated_at）"""
        base_cols = [
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ]
        await self.ensure_columns(table, base_cols)


async def migrate(url: str) -> None:
    mgr = DBManager(url)
    await mgr.connect()
    m = Migration(mgr, url)
    db_label = "SQLite" if m.is_sqlite else "PostgreSQL"
    print(f"[migrate] 数据库: {db_label}  ({url})\n")

    # 1. product 表（老库缺失时兜底创建；正常情况由 ORM create_all() 创建）
    print("[migrate] 检查 product ...")
    await m.ensure_table("product", CREATE_PRODUCT)
    await m.ensure_base_columns("product")

    # 2. product 表新列（schema 演进示例）
    if await m.table_exists("product"):
        print("[migrate] 检查 product 新列 ...")
        await m.ensure_columns("product", PRODUCT_NEW_COLUMNS)
    else:
        print("[migrate] product 表不存在，跳过列迁移（首次部署由 create_all() 创建）")

    # 3. 打印结果
    if await m.table_exists("product"):
        print("\n[migrate] 当前 product 表列:")
        for name in await m.get_existing_columns("product"):
            print(f"    {name}")
    else:
        print("\n[migrate] product 表尚未创建，首次启动时由 create_all() 自动创建。")

    print("\n[migrate] ✓ 迁移完成。")
    await mgr.disconnect()


def main():
    url = DEFAULT_URL
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--url" and i + 1 < len(args):
            url = args[i + 1]
            i += 2
        else:
            i += 1
    asyncio.run(migrate(url))


if __name__ == "__main__":
    main()
