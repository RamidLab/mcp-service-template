"""数据字典工具 — 自动扫描 ORM 模型元数据。"""

__all__ = ["dict_meta"]

from typing import Any

from fastmcp.tools import tool

from service_mcp.utils.enums import Errcode


@tool(
    name="dict_meta",
    title="获取实体元数据",
    description="自动扫描 ORM 模型，返回字段定义、枚举选项、关系图谱",
    tags={"domain_tool"},
)
async def dict_meta(entity_type: str | None = None) -> dict[str, Any]:
    """
    获取实体元数据（自动扫描 ORM 模型）。

    Args:
        entity_type: 实体类型，如 "product"。不传则返回全部。

    Returns:
        实体的字段定义、枚举选项、关系图谱
    """
    try:
        from service_mcp.auth.discovery import get_entity_metadata

        metadata = get_entity_metadata()

        if entity_type:
            data = metadata.get(entity_type)
            if data is None:
                return {
                    "code": Errcode.RECORD_NOT_FOUND,
                    "message": f"实体 {entity_type} 不存在",
                    "data": None,
                }
            return {"code": Errcode.SUCCESS, "message": "获取成功", "data": data}

        return {"code": Errcode.SUCCESS, "message": "获取成功", "data": metadata}

    except Exception as e:
        return {"code": Errcode.FAIL, "message": f"获取元数据失败: {e!s}", "data": None}
