__all__ = [
    "CacheConfig",
    "DatabaseConfig",
    "InfluxDBConfig",
    "MySQLConfig",
    "PageData",
    "PaginationMetadata",
    "PaginationParams",
    "PostgresqlConfig",
    "RedisConfig",
    "SQLiteConfig",
]

from functools import lru_cache
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    TypeAdapter,
    field_validator,
    model_validator,
)

from service_mcp.models import StorageConfigBase
from service_mcp.utils.enums import NodeStatus
from service_mcp.utils.path_utils import PROJECT_ROOT


T = TypeVar("T")


@lru_cache(maxsize=1)
def _get_db_adapter() -> TypeAdapter:
    """使用单例模式获取数据库适配器"""
    return TypeAdapter(
        Annotated[
            Annotated[SQLiteConfig, "sqlite"]
            | Annotated[MySQLConfig, "mysql"]
            | Annotated[PostgresqlConfig, "postgresql"]
            | Annotated[InfluxDBConfig, "influxdb"],
            Field(discriminator="db_type"),
        ]
    )


@lru_cache(maxsize=1)
def _get_cache_adapter() -> TypeAdapter:
    """使用单例模式获取缓存适配器"""
    return TypeAdapter(
        Annotated[Annotated[RedisConfig, "redis"], Field(discriminator="cache_type")]
    )


class DatabaseConfig(StorageConfigBase):
    """数据库配置基类"""

    db_type: Literal["sqlite", "mysql", "postgresql", "influxdb"] = Field(
        default="sqlite", title="数据库类型"
    )
    db_host: str = Field(default="memory", title="数据库主机")
    db_port: int = Field(default=80, title="数据库端口")
    db_sql_echo: Literal["open", "close"] = Field(default="close", title="SQL命令输出")
    db_pool_size: int = Field(default=5, title="连接池大小")

    status: NodeStatus = Field(default=NodeStatus.Unknown, title="数据库状态")

    def __new__(cls, **data):
        if cls is DatabaseConfig:
            adapter = _get_db_adapter()
            data.setdefault("db_type", "sqlite")
            return adapter.validate_python(data)
        return object.__new__(cls)

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """自定义模型验证方法，根据类型选择数据库适配器"""
        if cls is DatabaseConfig:
            return _get_db_adapter().validate_python(obj, **kwargs)
        return super().model_validate(obj, **kwargs)

    @property
    def url(self) -> str:
        raise NotImplementedError("url 属性未实现")

    def _do_test(self, timeout: int) -> None:
        raise NotImplementedError("_do_test 方法未实现")

    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        raise NotImplementedError("_classify_error 方法未实现")


class SQLiteConfig(DatabaseConfig):
    """SQLite 数据库配置"""

    db_type: Literal["sqlite"] = "sqlite"
    db_host: str = Field(
        default="memory",
        title="数据库主机",
        min_length=1,
        description="默认 memory，Sqlite 数据库可选文件路径（存放项目根目录下的 .cache/sqlite/ 文件夹，"
        "如：test.db或example/test.db，实际路径为：.cache/sqlite/test.db或.cache/sqlite/example/test.db）",
    )

    def _build_url(self, async_driver: bool = True) -> str:
        """内部方法：根据需要返回同步或异步连接字符串"""
        prefix = "sqlite+aiosqlite" if async_driver else "sqlite"
        if self.db_host == "memory":
            return f"{prefix}:///:memory:"
        path = PROJECT_ROOT.joinpath(".cache/sqlite", self.db_host or "")
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"{prefix}:///{path.as_posix()}"

    @property
    def url(self) -> str:
        return self._build_url(async_driver=True)

    def _do_test(self, timeout: int) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy import text as sa_text

        engine = create_engine(
            self._build_url(async_driver=False),
            echo=self.db_sql_echo == "open",
        )
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        engine.dispose()

    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        return NodeStatus.Error, f"SQLite 错误: {getattr(exc, 'orig', exc)}"


class MySQLConfig(DatabaseConfig):
    """MySQL 数据库配置"""

    db_type: Literal["mysql"] = "mysql"
    db_host: str = Field(default="127.0.0.1", title="数据库主机")
    db_port: int = Field(default=3306, title="数据库端口号")
    db_username: str = Field(default="root", title="数据库用户名")
    db_password: SecretStr = Field(default=SecretStr("root"), title="数据库密码")
    db_main: str = Field(default="service_data", title="数据库主键")

    def _build_url(self, async_driver: bool = True) -> str:
        driver = "asyncmy" if async_driver else "pymysql"
        user = self.db_username
        pwd = self.db_password.get_secret_value()
        base = f"mysql+{driver}://{user}:{pwd}@{self.db_host}:{self.db_port}/{self.db_main}"
        return base

    @property
    def url(self) -> str:
        return self._build_url(async_driver=True)

    def _do_test(self, timeout: int) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy import text as sa_text

        engine = create_engine(
            self._build_url(async_driver=False),
            echo=self.db_sql_echo == "open",
            connect_args={"connect_timeout": timeout},
        )
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        engine.dispose()

    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        return self._classify_mysql_error(exc)

    @staticmethod
    def _classify_mysql_error(exc: Exception) -> tuple[NodeStatus, str]:
        import pymysql

        orig = getattr(exc, "orig", exc)
        if isinstance(orig, pymysql.err.OperationalError):
            code = orig.args[0] if orig.args else None
            if code in (2003, 2002):
                return NodeStatus.Inactive, "MySQL 服务未启动或主机/端口不可达"
            if code == 1045:
                return NodeStatus.AuthFailed, "MySQL 用户名或密码错误"
            if code == 1044:
                return NodeStatus.AuthFailed, "MySQL 用户无权访问该数据库"
        elif isinstance(orig, pymysql.err.InternalError):
            return NodeStatus.Error, f"MySQL 内部错误: {orig}"
        elif isinstance(orig, pymysql.err.ProgrammingError):
            return NodeStatus.Error, f"MySQL 语法/配置错误: {orig}"
        return NodeStatus.Error, f"MySQL 错误: {orig}"


class PostgresqlConfig(DatabaseConfig):
    """PostgreSQL 数据库配置"""

    db_type: Literal["postgresql"] = "postgresql"
    db_host: str = Field(default="127.0.0.1", title="数据库主机")
    db_port: int = Field(default=5432, title="数据库端口号")
    db_username: str = Field(default="postgres", title="数据库用户名")
    db_password: SecretStr = Field(default=SecretStr("postgres"), title="数据库密码")
    db_main: str = Field(default="service_data", title="数据库主键")

    def _build_url(self, async_driver: bool = True) -> str:
        driver = "asyncpg" if async_driver else "psycopg2"
        user = self.db_username
        pwd = self.db_password.get_secret_value()
        base = f"postgresql+{driver}://{user}:{pwd}@{self.db_host}:{self.db_port}/{self.db_main}"
        return base

    @property
    def url(self) -> str:
        return self._build_url(async_driver=True)

    def _do_test(self, timeout: int) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy import text as sa_text

        engine = create_engine(
            self._build_url(async_driver=False),
            echo=self.db_sql_echo == "open",
            connect_args={"connect_timeout": timeout},
        )
        with engine.connect() as conn:
            conn.execute(sa_text("SELECT 1"))
        engine.dispose()

    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        return self._classify_pg_error(exc)

    @staticmethod
    def _classify_pg_error(exc: Exception) -> tuple[NodeStatus, str]:
        import psycopg2

        orig = getattr(exc, "orig", exc)
        if isinstance(orig, psycopg2.Error):
            pg_code = getattr(orig, "pgcode", "")
            if pg_code:
                if pg_code.startswith("08"):
                    return (
                        NodeStatus.Inactive,
                        f"PostgreSQL 服务未启动或连接被拒绝 (SQLSTATE: {pg_code})",
                    )
                if pg_code == "28P01":
                    return NodeStatus.AuthFailed, "PostgreSQL 密码错误"
                if pg_code == "28000":
                    return NodeStatus.AuthFailed, "PostgreSQL 认证失败 (用户或配置错误)"
                if pg_code == "53300":
                    return NodeStatus.Error, "PostgreSQL 连接数过多"
                if pg_code in ("3D000", "3F000"):
                    return NodeStatus.Error, "PostgreSQL 数据库或 schema 不存在"
        error_msg = str(orig)
        if "connection refused" in error_msg.lower() or "is the server running" in error_msg:
            return NodeStatus.Inactive, "PostgreSQL 服务未启动或端口不通"
        if (
            "could not translate host name" in error_msg.lower()
            or "name or service not known" in error_msg.lower()
        ):
            return NodeStatus.Inactive, "PostgreSQL 主机地址无法解析，请检查网络配置"
        if "password authentication failed" in error_msg.lower():
            return NodeStatus.AuthFailed, "PostgreSQL 密码认证失败"
        return NodeStatus.Error, f"PostgreSQL 错误: {orig}"


class InfluxDBConfig(DatabaseConfig):
    """InfluxDB 配置"""

    db_type: Literal["influxdb"] = Field(default="influxdb", title="数据库类型")
    db_host: str = Field(default="localhost", title="数据库主机")
    db_port: int = Field(default=8086, title="数据库端口")
    db_ssl_enabled: bool = Field(default=False, title="是否启用 HTTPS")
    db_main: str = Field(default="service_data", title="默认桶")
    influxdb_org: str = Field(..., title="组织")
    influxdb_token: SecretStr = Field(..., alias="influxdb_token", title="Token")

    @property
    def url(self) -> str:
        scheme = "https" if self.db_ssl_enabled else "http"
        return f"{scheme}://{self.db_host}:{self.db_port}"

    def _do_test(self, timeout: int) -> None:
        from influxdb_client import InfluxDBClient

        tok = self.influxdb_token.get_secret_value()
        with InfluxDBClient(
            url=self.url, token=tok, org=self.influxdb_org, timeout=timeout * 1000
        ) as client:
            if not client.ping():
                raise ConnectionError("InfluxDB ping 失败")

    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        return self._classify_influx_error(exc)

    @staticmethod
    def _classify_influx_error(exc: Exception) -> tuple[NodeStatus, str]:
        import requests
        from influxdb_client.rest import ApiException

        orig = getattr(exc, "orig", exc)
        if isinstance(orig, (requests.ConnectionError, ConnectionRefusedError, ConnectionError)):
            return NodeStatus.Inactive, "InfluxDB 服务未启动或网络不可达"
        if isinstance(orig, (requests.Timeout, TimeoutError)):
            return NodeStatus.Inactive, "InfluxDB 连接超时"
        if isinstance(orig, ApiException):
            if orig.status == 401:
                return NodeStatus.AuthFailed, "InfluxDB 认证失败 (Token 错误)"
            if orig.status == 403:
                return NodeStatus.AuthFailed, "InfluxDB 无权限访问"
            return NodeStatus.Error, f"InfluxDB API 错误: HTTP {orig.status}"
        return NodeStatus.Error, f"InfluxDB 错误: {exc}"


class CacheConfig(StorageConfigBase):
    """缓存配置基类（自动注册子类）"""

    cache_type: Literal["redis"] = Field(default="redis", title="缓存类型")
    cache_host: str = Field(default="127.0.0.1", title="缓存主机")
    cache_port: int = Field(default=6379, title="缓存绑定端口")

    status: NodeStatus = Field(default=NodeStatus.Unknown, title="缓存服务状态")

    def __new__(cls, **data):
        if cls is CacheConfig:
            adapter = _get_cache_adapter()
            data.setdefault("cache_type", "redis")
            return adapter.validate_python(data)
        return object.__new__(cls)

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """自定义模型验证方法，根据类型选择缓存适配器"""
        if cls is CacheConfig:
            return _get_cache_adapter().validate_python(obj, **kwargs)
        return super().model_validate(obj, **kwargs)

    @property
    def url(self) -> str:
        raise NotImplementedError("url 属性未实现")

    def _do_test(self, timeout: int) -> None:
        raise NotImplementedError("_do_test 方法未实现")

    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        raise NotImplementedError("_classify_error 方法未实现")


class RedisConfig(CacheConfig):
    """
    缓存配置

    Args:
        cache_host: 缓存主机，默认 None
        cache_port: 缓存端口，默认 None
        cache_pass: 缓存密码，默认 None
        timeout: 缓存超时时间，默认 5 秒
        databases: 逻辑数据库数量，默认 16
        ttl_seconds: 缓存过期时间，默认 300 秒
        max_size: 缓存最大大小，默认 1024MB
        cache_type: 缓存类型，默认 memory，可选 memory, redis
        status: 缓存服务状态，默认 Unknown
    """

    cache_type: Literal["redis"] = Field(default="redis", title="缓存类型")
    cache_host: str = Field(default="127.0.0.1", title="缓存主机")
    cache_port: int = Field(default=6379, title="缓存绑定端口")
    cache_pass: SecretStr | None = Field(default=None, title="缓存密码")
    cache_main: int = Field(default=0, title="主数据库索引")
    databases: int = Field(default=16, title="逻辑数据库数量", description="默认16个，索引从0到15")
    timeout: int = Field(default=5, title="缓存超时时间（秒）", description="缓存超时时间（秒）")
    key_prefix: str | None = Field(default=None, title="键前缀", description="键前缀，默认空字符串")
    ttl_seconds: int = Field(default=300, title="缓存过期时间（秒）")
    max_size: int = Field(default=1024, title="缓存最大大小（MB）")
    cache_pool_size: int = Field(
        default=10,
        title="连接池最大连接数",
        description="根据预估的并发量调整，默认10。对于Async Web应用，建议设为5-20。",
    )

    @property
    def url(self) -> str:
        auth = f"{self.cache_pass.get_secret_value()}@" if self.cache_pass else ""
        return f"redis://{auth}{self.cache_host}:{self.cache_port}/{self.cache_main}"

    def _do_test(self, timeout: int) -> None:
        """
        执行 Redis 连接测试，包括 ping 和数据库选择

        Args:
            timeout: 连接超时秒数（覆盖 config.timeout）
        Returns:
            None
        """
        import redis

        # 处理密码（SecretStr -> 明文）
        password = self.cache_pass.get_secret_value() if self.cache_pass else None

        # 创建 Redis 客户端（连接池延迟建立实际连接；redis-py 2.x API）
        client = redis.Redis(
            host=self.cache_host,
            port=self.cache_port,
            password=password,
            socket_timeout=timeout,
        )

        # 测试基本连通性（ping 失败会抛出异常）
        client.ping()

        # 测试目标数据库是否可用（有效索引范围 0 ~ databases-1）
        cache_index = self.cache_main
        if cache_index < 0 or cache_index >= self.databases:
            raise ValueError(
                f"数据库索引 {cache_index} 超出允许范围 [0, {self.databases - 1}]，"
                f"请检查 main_db 设置"
            )

        # 执行 SELECT 命令验证数据库是否存在
        try:
            client.execute_command("SELECT", cache_index)
        except redis.exceptions.ResponseError as e:
            # Redis 返回 "ERR DB index is out of range"
            raise redis.exceptions.ResponseError(
                f"数据库索引 {cache_index} 无效或超出服务器允许范围: {e}"
            ) from e

        # 释放连接（redis-py 2.x 无 close，连接随对象销毁自动释放）
        del client

    def _classify_error(self, exc: Exception) -> tuple[NodeStatus, str]:
        return self._classify_redis_error(exc)

    @staticmethod
    def _classify_redis_error(exc: Exception) -> tuple[NodeStatus, str]:
        """
        分类 Redis 异常，返回状态枚举和消息。

        Args:
            exc: Redis 异常对象
        Returns:
            - 状态枚举
            - 响应消息
        """

        import redis.exceptions as redis_exc

        # 认证失败（redis-py 2.x）
        if isinstance(exc, redis_exc.AuthenticationError):
            return NodeStatus.AuthFailed, "Redis 认证失败（用户名/密码错误或权限不足）"

        # 连接层异常（服务未启动、网络不通、超时等）
        if isinstance(exc, redis_exc.ConnectionError):
            msg = str(exc).lower()
            if "invalid password" in msg or "authentication" in msg:
                # 保险：部分版本将密码错误包装在 ConnectionError 中
                return NodeStatus.AuthFailed, "Redis 认证失败（密码错误）"
            if "connection refused" in msg or "timed out" in msg:
                return NodeStatus.Inactive, "Redis 服务未启动或主机/端口不可达"
            return NodeStatus.Inactive, f"Redis 连接失败: {exc}"

        # 响应错误（如 SELECT 无效数据库、命令错误）
        if isinstance(exc, redis_exc.ResponseError):
            err_lower = str(exc).lower()
            if "db index" in err_lower or "out of range" in err_lower:
                return NodeStatus.Error, f"Redis 数据库索引超出范围: {exc}"
            return NodeStatus.Error, f"Redis 命令执行错误: {exc}"

        # 其他未捕获异常
        return NodeStatus.Error, f"Redis 错误: {exc}"


class PaginationParams(BaseModel):
    """
    分页请求参数（客户端传入）

    Args:
        page: 当前页码，从1开始，默认 1
        page_size: 每页记录数，最大200，默认 20

    """

    page: int = Field(default=1, ge=1, title="当前页码", description="当前页码，从1开始")
    page_size: int = Field(
        default=20, ge=1, le=200, title="每页记录数", description="每页记录数，最大200"
    )

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        if v > 200:
            raise ValueError("每页记录数 page_size 不能超过 200")
        return v

    @property
    def offset(self) -> int:
        """计算数据库偏移量（跳过记录数）"""
        return (self.page - 1) * self.page_size

    def limit_offset(self) -> tuple[int, int]:
        """返回 (limit, offset) 元组，便于数据库查询"""
        return self.page_size, self.offset


class PaginationMetadata(BaseModel):
    """
    分页元数据（响应中的分页信息）

    Args:
        page: 当前页码
        page_size: 每页记录数
        total: 总记录数
        total_pages: 总页数
        has_next: 是否有下一页
        has_prev: 是否有上一页
    """

    page: int = Field(..., title="当前页码", description="当前页码")
    page_size: int = Field(..., title="每页记录数", description="每页记录数")
    total: int = Field(..., ge=0, title="总记录数", description="总记录数")
    total_pages: int = Field(..., ge=0, title="总页数", description="总页数")
    has_next: bool = Field(..., title="是否有下一页", description="是否有下一页")
    has_prev: bool = Field(..., title="是否有上一页", description="是否有上一页")

    @model_validator(mode="after")
    def compute_pages(self) -> "PaginationMetadata":
        """根据 total 和 page_size 自动计算总页数和前后页标志"""
        if self.total_pages == 0 and self.total > 0 and self.page_size > 0:
            # 如果没有手动设置 total_pages，自动计算
            object.__setattr__(
                self, "total_pages", (self.total + self.page_size - 1) // self.page_size
            )
        object.__setattr__(self, "has_next", self.page < self.total_pages)
        object.__setattr__(self, "has_prev", self.page > 1)
        return self

    @classmethod
    def from_params(cls, params: PaginationParams, total: int) -> "PaginationMetadata":
        """从请求参数和总记录数构造分页元数据"""
        page_size = params.page_size
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            page=params.page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )


class PageData(BaseModel, Generic[T]):
    """
    分页响应数据（通用）

    Args:
        items: 当前页的数据列表
        pagination: 分页信息
    """

    items: list[T] = Field(..., title="当前页的数据列表", description="当前页的数据列表")
    pagination: PaginationMetadata = Field(..., title="分页信息", description="分页信息")

    @classmethod
    def create(cls, items: list[T], params: PaginationParams, total: int) -> "PageData[T]":
        """便捷构造方法"""
        pagination = PaginationMetadata.from_params(params, total)
        return cls(items=items, pagination=pagination)
