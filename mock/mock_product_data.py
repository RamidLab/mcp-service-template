"""演示数据生成器：为示例实体 Product / ProductPrice 生成 mock 数据。

用法:
    uv run python mock/mock_product_data.py

对配置中所有数据库（default / pg-default / mysql-default / influxdb-default）
执行 drop_all + create_all 后写入演示数据。新增实体时：
    1. 在 TABLE_META 添加 (表名 → (ORM 类, InfluxDB measurement))
    2. 编写 generate_xxx_data() 生成函数
    3. 在 _build_tags_fields 补充 InfluxDB 的 tags/fields 映射
    4. 在 main() 中按依赖顺序调用 insert_data
"""

import asyncio
import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from faker import Faker

from service_mcp.db.core import DBManager, InfluxDBManager, get_manager
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.utils.enums import ProductCategory
from service_mcp.utils.log import get_logger


logger = get_logger(__name__)

fake = Faker("zh_CN")

TABLE_META = {
    "product": (Product, "product"),
    "product_price": (ProductPrice, "product_price"),
}


def generate_product_data() -> list[dict[str, Any]]:
    """
    生成商品数据

    Returns:
        商品数据列表
    """
    products = []
    for i in range(1, 21):
        products.append(
            {
                "id": i,
                "code": f"P{i:04d}",
                "name": f"{fake.company()}旗舰商品{i:02d}号",
                "category": random.choice(list(ProductCategory.__members__.values())),
                "price": Decimal(str(round(random.uniform(1, 500), 2))),
                "stock": random.randint(0, 200),
                "is_active": random.choice([True, True, False]),
                "remark": fake.sentence(nb_words=6) if random.random() > 0.5 else None,
            }
        )
    return products


def generate_product_price_data(product_ids: list[int]) -> list[dict[str, Any]]:
    """
    生成商品价格数据（每个商品约 30 个自然日的价格序列）

    Args:
        product_ids: 商品 ID 列表

    Returns:
        商品价格数据列表
    """
    prices = []
    pid = 1
    for product_id in product_ids:
        start = date.today() - timedelta(days=30)
        unit = Decimal(str(round(random.uniform(1, 100), 2)))
        for day_offset in range(30):
            d = start + timedelta(days=day_offset)
            unit = Decimal(str(round(float(unit) * (1 + random.uniform(-0.03, 0.03)), 2)))
            prices.append(
                {
                    "id": pid,
                    "product_id": product_id,
                    "price_date": d,
                    "price": unit,
                    "version": 0,
                }
            )
            pid += 1
    return prices


def _build_tags_fields(
    table_name: str, row: dict[str, Any]
) -> tuple[dict[str, str], dict[str, Any]]:
    """将 RDBMS 行转为 InfluxDB tags/fields。"""
    if table_name == "product":
        tags = {
            "code": row.get("code", ""),
        }
        fields = {
            "name": row.get("name", ""),
            "category": row["category"].value
            if hasattr(row.get("category"), "value")
            else row.get("category", 1),
            "price": float(row["price"]) if row.get("price") is not None else 0.0,
            "stock": int(row.get("stock", 0)),
            "is_active": bool(row.get("is_active", True)),
        }
    elif table_name == "product_price":
        tags = {
            "product_id": str(row.get("product_id", "")),
            "price_date": row["price_date"].isoformat()
            if isinstance(row.get("price_date"), date)
            else str(row.get("price_date", "")),
        }
        fields = {
            "price": float(row["price"]) if row.get("price") is not None else 0.0,
            "version": int(row.get("version", 0)),
        }
    else:
        logger.warning(f"未定义 InfluxDB tags/fields 映射: {table_name}")
        tags, fields = {}, {}

    return tags, fields


async def insert_data(
    mgr: DBManager | InfluxDBManager, table_name: str, data: list[dict[str, Any]]
) -> None:
    """
    通用数据插入，根据表名选择 ORM 类或 InfluxDB 写入

    Args:
        mgr: 数据库管理器实例
        table_name: 表名
        data: 要插入的记录数据列表，每个记录是一个字典，键为字段名，值为字段值
    """
    orm_class, measurement = TABLE_META.get(table_name, (None, None))
    if orm_class is None:
        raise ValueError(f"不支持的表: {table_name}")

    if isinstance(mgr, InfluxDBManager):
        points = []
        for row in data:
            tags, fields = _build_tags_fields(table_name, row)

            # 确定时间戳
            ts: Any = row.get("price_date")
            if ts is None:
                ts = datetime.now(UTC)
            elif isinstance(ts, date) and not isinstance(ts, datetime):
                ts = datetime.combine(ts, datetime.min.time(), tzinfo=UTC)

            points.append(
                {
                    "measurement": measurement,
                    "tags": tags,
                    "fields": fields,
                    "time": ts.isoformat() if isinstance(ts, datetime) else str(ts),
                }
            )
        await mgr.write(points)
        logger.info(f"已向 InfluxDB 写入 {len(data)} 条记录 ({table_name})")

    elif isinstance(mgr, DBManager):
        async with mgr.get_session() as session:
            orm_columns = {c.name for c in orm_class.__table__.columns}
            orm_objects = [
                orm_class(**{k: v for k, v in row.items() if k in orm_columns}) for row in data
            ]
            session.add_all(orm_objects)
            await session.commit()
        logger.info(f"已向 RDBMS 写入 {len(data)} 条记录 ({table_name})")


async def main():
    """主函数，负责生成并插入演示数据到数据库"""
    for item in ["default", "pg-default", "mysql-default", "influxdb-default"]:
        # 获取数据库管理器（异步）
        manager_info = await get_manager("db", item)
        mgr = manager_info["mgr"]
        db_type = manager_info["db_type"]

        logger.info(f"开始处理数据库 {item}, 类型: {db_type}")

        try:
            if db_type != "influxdb":
                await mgr.drop_all()
                await mgr.create_all()
                logger.info("ORM 表已就绪")

            # 生成商品数据
            product_data = generate_product_data()
            product_ids = [d["id"] for d in product_data]
            await insert_data(mgr, "product", product_data)

            # 生成商品价格数据（依赖商品 ID）
            price_data = generate_product_price_data(product_ids)
            await insert_data(mgr, "product_price", price_data)

            logger.info(f"所有 mock 数据已成功生成并插入 {item} 数据库")

        except Exception as e:
            logger.exception(f"处理数据库 {item} 时发生错误: {e}")

        finally:
            # 关闭连接
            await mgr.disconnect()
            logger.info(f"数据库 {item} 连接已关闭")


if __name__ == "__main__":
    asyncio.run(main())
