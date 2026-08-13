import asyncio
import random
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from faker import Faker

from service_mcp.db.core import InfluxDBManager


fake = Faker("zh_CN")


def random_point(measurement: str | None = None) -> dict[str, Any]:
    """
    生成一个随机数据点，如果未提供 measurement，则自动生成唯一名称

    Args:
        measurement: 测量值，默认自动生成唯一名称

    Returns:
        包含测量值、标签和字段值的字典
    """
    if measurement is None:
        measurement = f"test_{int(datetime.now().timestamp() * 1000)}_{random.randint(1000, 9999)}"
    return {
        "measurement": measurement,
        "tags": {
            "host": fake.hostname(),
            "region": fake.city(),
            "env": random.choice(["dev", "test", "prod"]),
        },
        "fields": {
            "cpu": round(random.uniform(0, 100), 2),
            "memory": random.randint(100, 1024),
            "temp": round(random.uniform(-10, 40), 1),
        },
        "time": datetime.now(UTC),
    }


def multiple_points(n: int) -> list[dict]:
    """
    生成多个随机数据点

    Args:
        n: 数据点数量

    Returns:
        包含 n 个随机数据点的列表
    """
    return [random_point() for _ in range(n)]


async def write_and_verify(
    mgr: InfluxDBManager,
    data: Any,  # 要写入的数据，可以是 point 字典、Point 对象、列表等
    measurement: str | None = None,
    *,
    expect_count: int = 1,
    check_one: bool = True,
) -> None:
    """
    通用写入并验证的辅助函数

    Args:
        mgr: InfluxDBManager 实例
        data: 要写入的数据，可以是 point 字典、Point 对象、列表等
        measurement: 测量值，默认从 data 中提取
        expect_count: 预期查询结果数量，默认 1
        check_one: 是否额外验证第一个记录，默认 True

    Returns:
        None
    """
    # 记录写入前的 measurement 名称（用于查询）
    if measurement is None:
        if isinstance(data, dict) and "measurement" in data:
            measurement = data["measurement"]
        elif hasattr(data, "measurement"):
            measurement = data.measurement
        else:
            raise ValueError("无法自动推断 measurement，请显式提供")

    await mgr.write(data)
    await asyncio.sleep(0.1)

    query = f'''
        from(bucket: "test")
        |> range(start: -1h)
        |> filter(fn: (r) => r._measurement == "{measurement}")
        |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    rows = await mgr.query(query)
    assert len(rows) >= expect_count

    if check_one and rows:
        if isinstance(data, dict):
            fields = data.get("fields", {})
        elif hasattr(data, "fields"):
            fields = data.fields
        else:
            fields = {}
        for k, v in fields.items():
            assert (
                rows[0].get(k) == pytest.approx(v) if isinstance(v, float) else rows[0].get(k) == v
            )


@pytest.fixture(params=["influxdb"])
async def influxdb_manager(
    request, db_urls: dict[str, str]
) -> AsyncGenerator[InfluxDBManager, Any]:
    """
    InfluxDB 连接管理器

    Args:
        request: pytest 请求对象
        db_urls: 包含 InfluxDB 数据库 URL 的字典

    Returns:
        InfluxDBManager 实例
    """
    mgr = InfluxDBManager(url=db_urls[request.param], token="your_token", org="test", bucket="test")
    await mgr.connect()
    yield mgr
    await mgr.disconnect()


class TestInfluxDBManager:
    @pytest.mark.asyncio
    async def test_connect_and_health(self, influxdb_manager: InfluxDBManager):
        """测试连接和健康检查"""
        assert await influxdb_manager.health_check() is True

    @pytest.mark.asyncio
    async def test_disconnect(self, influxdb_manager: InfluxDBManager):
        """测试断开连接"""
        await influxdb_manager.disconnect()
        assert await influxdb_manager.health_check() is False

    @pytest.mark.asyncio
    async def test_write_point(self, influxdb_manager: InfluxDBManager):
        """测试写入单个数据点"""
        point = random_point()
        await write_and_verify(influxdb_manager, point)

    @pytest.mark.asyncio
    async def test_write_records(self, influxdb_manager: InfluxDBManager):
        """测试写入多个数据点"""
        points = multiple_points(3)
        await influxdb_manager.write_records("bulk_test", points)
        query = 'from(bucket: "test") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "bulk_test")'
        rows = await influxdb_manager.query(query)
        assert len(rows) >= 3

    @pytest.mark.asyncio
    async def test_generic_write_with_dict(self, influxdb_manager: InfluxDBManager):
        """测试写入单个数据点"""
        point = random_point()
        await write_and_verify(influxdb_manager, point)

    @pytest.mark.asyncio
    async def test_generic_write_with_list(self, influxdb_manager: InfluxDBManager):
        """测试写入多个数据点"""
        points = [random_point() for _ in range(2)]
        await influxdb_manager.write(points)
        assert True

    @pytest.mark.asyncio
    async def test_query_one(self, influxdb_manager: InfluxDBManager):
        """测试查询单个数据点"""
        point = random_point()
        await write_and_verify(influxdb_manager, point, expect_count=1, check_one=True)

    @pytest.mark.asyncio
    async def test_unknown_query(self, influxdb_manager: InfluxDBManager):
        """测试查询不存在的测量值"""
        rows = await influxdb_manager.query(
            'from(bucket: "test") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "nonexistent")'
        )
        assert rows == []

    @pytest.mark.asyncio
    async def test_health_check_fail(self, influxdb_manager: InfluxDBManager):
        """测试健康检查失败"""
        await influxdb_manager.disconnect()
        assert await influxdb_manager.health_check() is False

    @pytest.mark.asyncio
    async def test_write_invalid_data(self, influxdb_manager: InfluxDBManager):
        """测试写入无效数据"""
        with pytest.raises(TypeError):
            await influxdb_manager.write(123)
