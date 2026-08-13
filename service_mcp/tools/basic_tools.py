__all__ = [
    "add_cache",
    "add_database",
    "delete_cache",
    "delete_database",
    "get_all_config",
    "get_tools_by_tag",
    "health",
    "review_abnormal_items",
    "update_cache",
    "update_database",
]

from typing import Any

from fastmcp.server.context import Context
from fastmcp.tools import tool

from service_mcp.auth.decorator import mcp_perm
from service_mcp.config import MCPSettings, get_settings
from service_mcp.handlers.query_handlers import QueryHandler
from service_mcp.models.common import UtilResponse
from service_mcp.models.schemas import (
    CacheConfig,
    DatabaseConfig,
    PageData,
    PaginationParams,
)
from service_mcp.tools import global_tool
from service_mcp.utils.common import check_result
from service_mcp.utils.enums import Errcode, NodeStatus


@tool(
    name="health",
    title="健康检查",
    description="检查MCP服务器健康状态，返回服务是否正常",
    tags={"sys_tool"},
)
@mcp_perm(resource="07", action="08")
async def health() -> UtilResponse[None]:
    # TODO: 检查系统服务是否正常
    return UtilResponse(code=Errcode.SUCCESS, message="服务正常")


@tool(
    name="review_abnormal_items",
    title="审核异常项",
    description="聚合查询所有需人工关注的异常记录（Product/ProductPrice），返回统一待办清单。可按严重程度、来源表筛选。",
    tags={"domain_tool"},
)
@mcp_perm(resource="08", action="01")
async def review_abnormal_items(
    params: PaginationParams,
    severity: str | None = None,
    source_table: str | None = None,
    db_name: str = "default",
) -> UtilResponse[PageData]:
    """聚合查询异常待办项。

    Args:
        params: 分页参数
        severity: 按严重程度筛选 —— critical / warning / info。不传则返回全部
        source_table: 按来源表筛选 —— product / product_price
        db_name: 数据库名称

    Returns:
        统一格式的待办清单，每条包含 source_table、summary、severity 等字段
    """
    handler = QueryHandler()
    return await handler.review_abnormal_items(params, severity, source_table, db_name)


@tool(
    name="get_tools_by_tag",
    title="根据标签查询工具",
    description="获取当前MCP服务器中所有带有指定标签的工具列表，返回工具名称、描述和标签信息。",
    tags={"sys_tool"},
)
@mcp_perm(resource="07", action="08")
async def get_tools_by_tag(tag: str, ctx: Context) -> UtilResponse[list[str]]:
    """
    根据标签筛选已注册的工具。

    Args:
        tag: 需要筛选的标签，例如 "sys_tool", "config_tool" 等。
        ctx: FastMCP 上下文对象，包含 FastMCP 服务器实例等信息。

    Returns:
        工具信息列表，每个工具包含：
        - name: 工具名称
        - description: 工具描述
        - tags: 该工具的所有标签列表
        - input_schema: 输入参数的 JSON Schema（可选）
    """
    mcp_server = ctx.fastmcp  # 获取 FastMCP 服务器实例
    all_tools = await mcp_server.list_tools()  # 异步获取所有工具
    matched = [item.name for item in all_tools if tag in item.tags]
    return UtilResponse(code=Errcode.SUCCESS, message="获取指定标签工具成功", data=matched)


@global_tool
@tool(name="get_all_config", title="获取所有配置", description="获取所有配置", tags={"config_tool"})
@mcp_perm(resource="07", action="08")
async def get_all_config(reload: bool = False) -> MCPSettings:
    """
    获取所有配置

    Returns:
        所有配置
    """
    return get_settings(reload)


@global_tool
@tool(
    name="add_database", title="添加数据库配置", description="添加数据库配置", tags={"config_tool"}
)
@mcp_perm(resource="07", action="07")
async def add_database(db_name: str, db_config: dict[str, Any]) -> UtilResponse[None]:
    """
    添加数据库配置

    Args:
        db_name: 数据库名称
        db_config: 数据库配置字典

    Returns:
        通用响应
    """
    settings = get_settings()
    result = check_result(settings.add_database(db_name, DatabaseConfig.model_validate(db_config)))
    settings.store()
    return result


@global_tool
@tool(name="add_cache", title="添加缓存配置", description="添加缓存配置", tags={"config_tool"})
@mcp_perm(resource="07", action="07")
async def add_cache(cache_name: str, cache_config: dict[str, Any]) -> UtilResponse[None]:
    """
    添加缓存配置

    Args:
        cache_name: 缓存名称
        cache_config: 缓存配置字典

    Returns:
        通用响应
    """
    settings = get_settings()
    result = check_result(settings.add_cache(cache_name, CacheConfig.model_validate(cache_config)))
    settings.store()
    return result


@global_tool
@tool(
    name="update_database",
    title="更新数据库配置",
    description="更新数据库配置",
    tags={"config_tool"},
)
@mcp_perm(resource="07", action="07")
async def update_database(
    db_name: str,
    db_config: dict[str, Any],
    new_db_name: str | None = None,
) -> UtilResponse[None]:
    """
    更新数据库配置

    Args:
        db_name: 当前数据库名称
        db_config: 数据库配置字典
        new_db_name: 可选，重命名数据库名称

    Returns:
        通用响应
    """
    settings = get_settings()
    db_config["status"] = db_config.get("status", NodeStatus.Unknown)
    result = check_result(
        settings.update_database(
            db_name=db_name,
            db_config=DatabaseConfig.model_validate(db_config),
            new_db_name=new_db_name if new_db_name and db_name != new_db_name else None,
        )
    )
    settings.store()
    return result


@global_tool
@tool(name="update_cache", title="更新缓存配置", description="更新缓存配置", tags={"config_tool"})
@mcp_perm(resource="07", action="07")
async def update_cache(
    cache_name: str,
    cache_config: dict[str, Any],
    new_cache_name: str | None = None,
) -> UtilResponse[None]:
    """
    更新缓存配置

    Args:
        cache_name: 当前缓存名称
        cache_config: 缓存配置字典
        new_cache_name: 可选，重命名缓存名称

    Returns:
        通用响应
    """
    settings = get_settings()
    cache_config["status"] = cache_config.get("status", NodeStatus.Unknown)
    result = check_result(
        settings.update_cache(
            cache_name=cache_name,
            cache_config=CacheConfig.model_validate(cache_config),
            new_cache_name=new_cache_name
            if new_cache_name and cache_name != new_cache_name
            else None,
        )
    )
    settings.store()
    return result


@global_tool
@tool(
    name="delete_database",
    title="删除数据库配置",
    description="删除数据库配置",
    tags={"config_tool"},
)
@mcp_perm(resource="07", action="07")
async def delete_database(db_name: str) -> UtilResponse[None]:
    """
    删除数据库配置

    Args:
        db_name: 数据库名称

    Returns:
        通用响应
    """
    settings = get_settings()
    result = check_result(settings.delete_database(db_name))
    settings.store()
    return result


@global_tool
@tool(name="delete_cache", title="删除缓存配置", description="删除缓存配置", tags={"config_tool"})
@mcp_perm(resource="07", action="07")
async def delete_cache(cache_name: str) -> UtilResponse[None]:
    """
    删除缓存配置

    Args:
        cache_name: 缓存名称

    Returns:
        通用响应
    """
    settings = get_settings()
    result = check_result(settings.delete_cache(cache_name))
    settings.store()
    return result
