from __future__ import annotations


__all__ = ["DBManager", "InfluxDBManager", "get_db_manager", "get_manager"]

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import (
    Any,
    Literal,
    TypedDict,
    TypeVar,
    cast,
    overload,
)

from influxdb_client import InfluxDBClient, Point, QueryApi
from influxdb_client.client.write_api import SYNCHRONOUS, WriteApi
from pydantic import SecretStr
from sqlalchemy import Inspector, func, inspect, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from service_mcp.config import get_settings
from service_mcp.db import RdbmsDBManager, TimeseriesDBManager
from service_mcp.error.exceptions import DatabaseConnectionError
from service_mcp.models.orm.base import Base
from service_mcp.models.schemas import InfluxDBConfig, PageData, PaginationParams


T = TypeVar("T", bound=Base)


class DBManager(RdbmsDBManager):
    """通用异步数据库管理器"""

    def __init__(
        self,
        url: str,
        echo: bool = False,
        pool_size: int = 10,
        max_overflow: int = 20,
    ):
        self._url: str = url
        self._echo: bool = echo
        self._pool_size: int = pool_size
        self._max_overflow: int = max_overflow
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._base: type[Base] = Base

    @property
    def engine(self) -> AsyncEngine:
        """获取异步引擎实例（必须已连接）"""
        assert self._engine is not None, "数据库未连接，请先调用 connect()"
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """获取会话工厂（必须已连接）"""
        assert self._session_factory is not None, "数据库未连接，请先调用 connect()"
        return self._session_factory

    @property
    def is_connected(self) -> bool:
        """数据库是否已连接（引擎已创建且未释放）"""
        return self._engine is not None

    async def connect(self) -> None:
        """连接数据库"""
        args = {
            "pool_size": self._pool_size,
            "max_overflow": self._max_overflow,
            "pool_recycle": 3600,  # 1小时回收连接
        }

        self._engine = create_async_engine(
            url=self._url,
            echo=self._echo,
            pool_pre_ping=True,
            **args if not self._url.startswith("sqlite") else {},
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def disconnect(self) -> None:
        """断开数据库连接"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            await asyncio.sleep(0.2)

    async def create_all(self) -> None:
        """创建所有 ORM 表"""
        if self._engine is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: self._base.metadata.create_all(bind=sync_conn))

    async def drop_all(self, _tables: list[str] | None = None, check_first: bool = True) -> None:
        """
        删除表（默认为所有表）。

        Args:
            _tables: 需要删除的表名列表。如果为 None，则删除所有 Base 元数据中定义的表。
            check_first: 是否在执行 DROP 前检查表是否存在，默认为 True（避免因表不存在而报错）。
        """
        if self._engine is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")

        if _tables is None:
            target_tables = None
        else:
            target_tables = []
            for name in _tables:
                table = self._base.metadata.tables.get(name)
                if table is None:
                    raise ValueError(f"表 '{name}' 不在元数据中")
                target_tables.append(table)

        async with self._engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: self._base.metadata.drop_all(
                    bind=sync_conn,
                    tables=target_tables,
                    checkfirst=check_first,
                )
            )

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """
        获取一个 AsyncSession 生成器，用于上下文管理

        Returns:
            会话生成器，用于上下文管理
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            yield session

    async def execute(self, statement: Any, params: dict | None = None) -> Any:
        """
        执行写操作，支持 Core / ORM 语句。
        返回 Result 对象。

        Args:
            statement: SQL 语句或 ORM 语句
            params: 参数字典，用于绑定参数

        Returns:
            Result 对象
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            result = await session.execute(statement, params or {})
            await session.commit()
            return result

    async def insert(self, obj: T) -> T:
        """
        插入单条 ORM 模型实例。

        Args:
            obj: ORM 模型实例（Base 子类）

        Returns:
            传入的对象（commit 后已包含 DB 生成的值，如自增 ID）
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            session.add(obj)
            await session.commit()
            await session.refresh(obj)
            return obj

    async def insert_batch(self, objs: list[T]) -> list[T]:
        """
        批量插入 ORM 模型实例。

        Args:
            objs: ORM 模型实例列表

        Returns:
            传入的对象列表（commit 后每个对象已包含 DB 生成的值）
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            session.add_all(objs)
            await session.commit()
            for obj in objs:
                await session.refresh(obj)
            return objs

    async def update_by_id(
        self,
        model: type[Base],
        record_id: int,
        values: dict[str, Any],
    ) -> type[Base]:
        """
        按主键更新单条 ORM 记录。

        Args:
            model: ORM 模型类。
            record_id: 主键 id。
            values: 待更新的字段 → 值字典。

        Returns:
            更新并刷新后的 ORM 实例。
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            instance = await session.get(model, record_id)
            if instance is None:
                raise ValueError(f"{model.__tablename__} 表中未找到 id={record_id} 的记录。")
            for field, value in values.items():
                setattr(instance, field, value)
            await session.commit()
            await session.refresh(instance)
            return instance

    async def delete_with_orphans(
        self,
        model: type[Base],
        record_id: int,
        orphan_statements: list[Any],
    ) -> None:
        """
        在同一事务内标记孤儿记录 + 删除父记录，原子提交。

        Args:
            model: 父记录的 ORM 模型类。
            record_id: 父记录主键 id。
            orphan_statements: 待执行的 UPDATE 语句列表（标记子记录为 Orphaned）。
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            for stmt in orphan_statements:
                await session.execute(stmt)
            instance = await session.get(model, record_id)
            if instance is None:
                raise ValueError(f"{model.__tablename__} 表中未找到 id={record_id} 的记录。")
            await session.delete(instance)
            await session.commit()

    async def delete_by_id(self, model: type[Base], record_id: int) -> None:
        """
        按主键删除单条 ORM 记录。

        Args:
            model: ORM 模型类。
            record_id: 主键 id。
        """
        await self.delete_with_orphans(model, record_id, [])

    async def delete_batch_with_orphans(
        self,
        model: type[Base],
        ids: list[int],
        orphan_statements: list[Any],
    ) -> int:
        """
        在同一事务内标记孤儿记录 + 批量删除父记录，原子提交。

        Args:
            model: 父记录的 ORM 模型类。
            ids: 父记录主键 id 列表。
            orphan_statements: 待执行的 UPDATE 语句列表（标记子记录为 Orphaned）。

        Returns:
            实际删除的记录数。
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        if not ids:
            return 0
        async with self._session_factory() as session:
            for stmt in orphan_statements:
                await session.execute(stmt)
            stmt = select(model).where(model.id.in_(ids))
            result = await session.execute(stmt)
            instances = result.scalars().all()
            for instance in instances:
                await session.delete(instance)
            await session.commit()
            return len(instances)

    async def delete_batch_by_ids(self, model: type[Base], ids: list[int]) -> int:
        """
        按主键批量删除 ORM 记录。

        Args:
            model: ORM 模型类。
            ids: 主键 id 列表。

        Returns:
            实际删除的记录数。
        """
        return await self.delete_batch_with_orphans(model, ids, [])

    async def update_batch_by_ids(
        self,
        model: type[Base],
        ids: list[int],
        values_list: list[dict[str, Any]],
    ) -> list[int]:
        """
        按主键批量更新 ORM 记录。

        Args:
            model: ORM 模型类。
            ids: 主键 id 列表。
            values_list: 与 *ids* 顺序对应的更新字段字典列表。

        Returns:
            更新成功的 id 列表。
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        if len(ids) != len(values_list):
            raise ValueError(
                f"更新数量不匹配：{len(ids)} 个 ID 与 {len(values_list)} 条数据不一致。"
            )
        async with self._session_factory() as session:
            updated_ids: list[int] = []
            for rid, vals in zip(ids, values_list):
                instance = await session.get(model, rid)
                if instance is None:
                    raise ValueError(f"{model.__tablename__} 表中未找到 id={rid} 的记录。")
                for field, value in vals.items():
                    setattr(instance, field, value)
                updated_ids.append(rid)
            await session.commit()
            return updated_ids

    async def get_all_tables(self) -> list[str]:
        """
        获取所有表名

        Returns:
            所有表名列表
        """
        if self._engine is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._engine.connect() as conn:

            def _get(sync_conn):
                inspector = cast("Inspector", inspect(sync_conn))
                return inspector.get_table_names()

            tables = await conn.run_sync(_get)
        return tables

    async def fetch_one(self, statement: Any, params: dict | None = None) -> dict | None:
        """
        执行查询并返回单行字典

        Args:
            statement: SQL 语句或 ORM 语句
            params: 参数字典，用于绑定参数

        Returns:
            单行字典，或 None 如果查询结果为空
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            result = await session.execute(statement, params or {})
            row = result.mappings().first()
            return dict(row) if row else None

    async def fetch_all(self, statement: Any, params: dict | None = None) -> list[dict]:
        """
        执行查询并返回字典列表

        Args:
            statement: SQL 语句或 ORM 语句
            params: 参数字典，用于绑定参数

        Returns:
            字典列表
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")
        async with self._session_factory() as session:
            result = await session.execute(statement, params or {})
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    async def paginate(
        self,
        model: type[Base],
        params: PaginationParams,
        where: list[Any] | None = None,
        order_by: list[Any] | None = None,
    ) -> PageData[dict[str, Any]]:
        """
        通用分页查询，返回 PageData。

        Args:
            model: SQLAlchemy ORM 模型（如 Product）
            params: 分页参数（page, page_size）
            where: 可选的过滤条件列表（如 Product.status == 1）
            order_by: 可选的排序字段列表（如 Product.launch_date.desc()）

        Returns:
            PageData 对象，包含分页数据和总数
        """
        if self._session_factory is None:
            raise RuntimeError("数据库未连接，请先调用 connect()")

        async with self._session_factory() as session:
            # 基础查询
            stmt = select(model)
            if where:
                stmt = stmt.where(*where)
            if order_by:
                stmt = stmt.order_by(*order_by)

            # 分页查询
            limit, offset = params.limit_offset()
            result = await session.execute(stmt.limit(limit).offset(offset))

            items = [
                {col.name: getattr(row, col.name) for col in model.__table__.columns.values()}
                for row in result.scalars().all()
            ]

            # 总数查询（复用相同的过滤条件）
            count_stmt = select(func.count()).select_from(model)
            if where:
                count_stmt = count_stmt.where(*where)
            total = (await session.execute(count_stmt)).scalar() or 0

        return PageData.create(items, params, total)

    async def health_check(self, timeout: float = 2.0) -> bool:
        """
        健康检查

        Args:
            timeout: 超时时间，默认 2.0 秒

        Returns:
            是否连接成功
        """
        # noinspection PyBroadException
        try:
            if self._engine is None:
                raise RuntimeError("数据库未连接，请先调用 connect()")
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


class InfluxDBManager(TimeseriesDBManager):
    """
    InfluxDB 管理器（生产就绪）

    - 写入：同步 WriteApi + asyncio.to_thread
    - 查询：同步 QueryApi + asyncio.to_thread
    """

    def __init__(self, url: str, token: SecretStr | str, org: str, bucket: str):
        self._url = url
        self._token = token.get_secret_value() if isinstance(token, SecretStr) else token
        self._org = org
        self._bucket = bucket
        self._client: InfluxDBClient | None = None
        self._write_api: WriteApi | None = None
        self._query_api: QueryApi | None = None

    async def connect(self, timeout: float = 30.0) -> None:
        """
        建立连接

        Args:
            timeout: 超时时间，默认 30.0 秒
        """

        def _connect(_timeout: float):
            client = InfluxDBClient(
                url=self._url,
                token=self._token,
                org=self._org,
                enable_gzip=True,
                timeout=int(_timeout * 1000),
            )
            write_api = client.write_api(write_options=SYNCHRONOUS)
            query_api = client.query_api()
            return client, write_api, query_api

        self._client, self._write_api, self._query_api = await asyncio.to_thread(_connect, timeout)

    async def disconnect(self) -> None:
        """在线程池中关闭连接"""
        if self._client:
            await asyncio.to_thread(self._client.close)
            self._client = None
            self._write_api = None
            self._query_api = None

    async def query(self, query: str, params: dict | None = None) -> list[dict]:
        """
        执行 Flux 查询

        Args:
            query: Flux 查询语句
            params: 参数字典，用于绑定参数

        Returns:
            查询结果列表，每个元素为一个字典，包含测量值、时间戳和字段值
        """
        if self._query_api is None:
            raise RuntimeError("InfluxDB 未连接，请先调用 connect()")

        query_api = self._query_api

        def _query():
            tables = query_api.query(query, org=self._org)
            results = []
            for table in tables:
                for record in table.records:
                    row = dict(record.values)
                    if record.get_measurement():
                        row["measurement"] = record.get_measurement()
                    if record.get_time():
                        row["time"] = record.get_time()
                    results.append(row)
            return results

        return await asyncio.to_thread(_query)

    async def write(self, data: Any) -> None:
        """
        写入数据

        Args:
            data: 要写入的数据，支持 Point、字典、列表、行协议等
        """
        if self._write_api is None:
            raise RuntimeError("InfluxDB 未连接，请先调用 connect()")
        write_api = self._write_api

        if isinstance(data, (int, float, bool)):
            raise TypeError(f"不支持的数据类型: {type(data)}，请使用 Point、字典或列表")

        if isinstance(data, Point):
            points = [data]
        elif isinstance(data, dict):
            points = [self._dict_to_point(data)]
        elif isinstance(data, list):
            points = []
            for item in data:
                if isinstance(item, Point):
                    points.append(item)
                elif isinstance(item, dict):
                    points.append(self._dict_to_point(item))
                else:
                    raise TypeError(f"列表中含有不支持的类型: {type(item)}")
        else:

            def _write_raw():
                write_api.write(
                    bucket=self._bucket,
                    record=data,
                    org=self._org,
                )

            await asyncio.to_thread(_write_raw)
            return

        if not points:
            return

        def _write_points():
            write_api.write(
                bucket=self._bucket,
                record=points,
                org=self._org,
            )

        await asyncio.to_thread(_write_points)

    async def write_point(
        self, measurement: str, tags: dict[str, str], fields: dict[str, Any], timestamp=None
    ) -> None:
        """
        写入单条记录

        Args:
            measurement: 测量值
            tags: 标签字典，键为标签名，值为标签值
            fields: 字段值字典，键为字段名，值为字段值
            timestamp: 时间戳，默认当前时间
        """
        point_dict = {
            "measurement": measurement,
            "tags": tags,
            "fields": fields,
            "time": timestamp,
        }
        await self.write(self._dict_to_point(point_dict))

    async def write_records(self, measurement: str, records: list[dict]) -> None:
        """
        写入多条记录

        Args:
            measurement: 测量值
            records: 记录列表，每个元素为一个字典，包含标签和字段值
        """
        enriched = []
        for rec in records:
            rec_copy = rec.copy()
            rec_copy["measurement"] = measurement
            enriched.append(rec_copy)
        await self.write(enriched)

    async def health_check(self) -> bool:
        """健康检查"""
        if self._client is None:
            return False
        # noinspection PyBroadException
        try:
            result = await asyncio.to_thread(self._client.ping)
            return bool(result)
        except Exception:
            return False

    @staticmethod
    def _dict_to_point(d: dict) -> Point:
        measurement = d.get("measurement")
        if not measurement:
            raise ValueError("字典必须包含 'measurement' 键")
        point = Point(measurement)
        for k, v in d.get("tags", {}).items():
            point.tag(k, v)
        for k, v in d.get("fields", {}).items():
            point.field(k, v)
        if "time" in d:
            point.time(d["time"])
        return point


class ManagerType(TypedDict):
    mgr: DBManager | TimeseriesDBManager
    db_type: str


class DBManagerResult(ManagerType):
    mgr: DBManager


class TimeseriesManagerResult(ManagerType):
    mgr: TimeseriesDBManager


_manager_cache: dict[Literal["db", "cache"], dict[str, ManagerType]] = {}


@overload
async def get_manager(_class: Literal["db"], db_name: str) -> DBManagerResult: ...


@overload
async def get_manager(_class: Literal["cache"], db_name: str) -> TimeseriesManagerResult: ...


async def get_manager(_class: Literal["db", "cache"], db_name: str) -> ManagerType:
    """
    获取数据库或缓存连接器

    Args:
        _class: 类型，"db" 或 "cache"
        db_name: 数据库名称

    Returns:
        数据库连接器实例，包含 mgr 和 db_type 键
    """
    manager_cache: dict[str, ManagerType] = _manager_cache.setdefault(_class, {})

    # 缓存命中：仅 DBManager 有可检查的连接状态，失效则清除重建
    if db_name in manager_cache:
        cached = manager_cache[db_name]
        mgr = cached["mgr"]
        if isinstance(mgr, DBManager):
            if mgr.is_connected:
                return cached
            del manager_cache[db_name]
        else:
            return cached

    settings = get_settings()
    db_config = settings.databases.get(db_name)
    if db_config is None:
        raise ValueError(f"数据库配置不存在: {db_name}")

    if isinstance(db_config, InfluxDBConfig):
        token = db_config.influxdb_token.get_secret_value()
        org = db_config.influxdb_org
        bucket = db_config.db_main
        if not token or not org or not bucket:
            raise ValueError("InfluxDB 必须提供 influxdb_token, influxdb_org 和 db_main (bucket)")

        influxdb_manager = InfluxDBManager(
            url=db_config.url,
            token=token,
            org=org,
            bucket=bucket,
        )
        await influxdb_manager.connect()

        if not await influxdb_manager.health_check():
            raise DatabaseConnectionError(f"InfluxDB {db_name} 连接成功但健康检查失败")

        manager_cache[db_name] = {
            "mgr": influxdb_manager,
            "db_type": db_config.db_type,
        }
    else:
        db_manager = DBManager(
            url=db_config.url,
            echo=db_config.db_sql_echo == "open",
            pool_size=db_config.db_pool_size,
            max_overflow=10,
        )
        await db_manager.connect()

        if not await db_manager.health_check():
            raise DatabaseConnectionError(f"数据库 {db_name} 连接成功但健康检查失败")

        manager_cache[db_name] = {
            "mgr": db_manager,
            "db_type": db_config.db_type,
        }

    return manager_cache[db_name]


async def get_db_manager(db_name: str = "default") -> DBManager:
    """获取数据库管理器实例（get_manager 的 db 类型快捷方式）。

    Args:
        db_name: 数据库配置名称。

    Returns:
        已连接并健康检查通过的 DBManager 实例。
    """
    return (await get_manager("db", db_name))["mgr"]  # type: ignore[return-value]
