"""CRUD 工具工厂 — 注册表驱动生成 add/update/delete 工具。

工具函数由实体注册表统一生成并注入模块命名空间，
避免 N 个实体 × 3 种操作的复制粘贴样板。
新增实体只需在 ``_ENTITIES`` 注册表中添加一行。
"""

__all__ = ["register_crud_tools"]

from typing import Any

from fastmcp.tools import tool
from pydantic import BaseModel

from service_mcp.error.exceptions import ToolError
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.orm.base import Base
from service_mcp.models.pydantic.product import (
    ProductCreate,
    ProductDelete,
    ProductPriceCreate,
    ProductPriceDelete,
    ProductPriceUpdate,
    ProductUpdate,
)
from service_mcp.tools.annotations import WRITE_DESTRUCTIVE, WRITE_IDEMPOTENT, WRITE_MUTATING


def _entity(
    name: str,
    plural: str,
    model: type[Base],
    resource: str,
    label: str,
    create: type[BaseModel] | None = None,
    update: type[BaseModel] | None = None,
    delete: type[BaseModel] | None = None,
    delete_lookup: str = "",
) -> dict[str, Any]:
    """构造实体注册项。

    Args:
        name: 单数工具名后缀（如 "product" → add_product）
        plural: 复数工具名后缀（如 "products" → add_products）
        model: ORM 模型类
        resource: 权限资源码（01=产品, 02=产品价格, 07=配置, 08=审计）
        label: 中文实体名（用于工具标题/描述）
        create: 创建 Pydantic 模型，None 表示不支持新增
        update: 更新 Pydantic 模型，None 表示不支持更新
        delete: 删除 Pydantic 模型，None 表示不支持删除
        delete_lookup: 删除定位方式说明（拼入删除工具描述）
    """
    return {
        "name": name,
        "plural": plural,
        "model": model,
        "resource": resource,
        "label": label,
        "create": create,
        "update": update,
        "delete": delete,
        "delete_lookup": delete_lookup,
    }


_ENTITIES: list[dict[str, Any]] = [
    _entity(
        "product",
        "products",
        Product,
        "01",
        "产品",
        create=ProductCreate,
        update=ProductUpdate,
        delete=ProductDelete,
        delete_lookup="通过 record_id、product_code 或 product_name 定位记录",
    ),
    _entity(
        "product_price",
        "product_prices",
        ProductPrice,
        "02",
        "产品价格",
        create=ProductPriceCreate,
        update=ProductPriceUpdate,
        delete=ProductPriceDelete,
        delete_lookup="通过 record_id，或 product_code + price_date 定位记录",
    ),
]


# 批量变更工具单次最大条数（防止超大请求拖垮服务，可按压测调整）
MAX_BATCH_SIZE = 200


def _check_batch_size(data_list: list) -> None:
    """批量条数超上限时抛业务错误（由工具层转换层收口为失败响应）。"""
    if len(data_list) > MAX_BATCH_SIZE:
        raise ToolError(f"批量条数 {len(data_list)} 超过上限 {MAX_BATCH_SIZE}，请分批提交")


def _tool_error_response(e: ToolError, data: dict[str, Any] | None = None) -> UtilResponse[Any]:
    """ToolError → 业务失败响应（中文 message + 业务 Errcode），绝不 500 化。

    转换层：handler 抛出的业务级可预期失败在此收口为 UtilResponse 返回，
    避免落入 FastMCP 通用协议错误（500 化）。只捕获 ToolError，数据库/程序
    错误（UniqueConflictError、DatabaseConnectionError 等）维持原路径。
    """
    return UtilResponse(code=e.code, message=str(e), data=data)


def _list_of(item_cls: type[BaseModel]) -> Any:
    """构造 ``list[item_cls]`` 类型对象。

    用 ``__class_getitem__`` 方法调用替代泛型下标语法，
    避免 IDE 对动态类型参数（运行时变量）报 "Parameters to generic types must be types"。
    """
    return list.__class_getitem__(item_cls)


def _annotate(annotations: dict[str, Any]) -> Any:
    """装饰器：在 @wraps 前注入精确类型注解。

    动态生成的工具函数签名无法直接写具体模型类型（data_cls 是运行时变量），
    本装饰器在 wraps 复制注解之前设置 __annotations__，
    使 inspect.signature（FastMCP 解析用）读到完整类型。
    """

    def decorator(func: Any) -> Any:
        func.__annotations__ = {**func.__annotations__, **annotations}
        return func

    return decorator


def _make_add_tool(ent: dict[str, Any], batch: bool) -> Any:
    """生成单条/批量新增工具函数。"""
    # 延迟导入避免与 auth.discovery 的循环依赖
    from service_mcp.auth.decorator import mcp_perm
    from service_mcp.handlers.add_handlers import AddHandler

    model: type[Base] = ent["model"]
    data_cls = ent["create"]
    name = f"add_{ent['plural'] if batch else ent['name']}"
    label = ent["label"]

    if batch:

        @tool(
            name=name,
            title=f"批量添加{label}",
            description=f"批量添加多条{label}记录",
            tags={"domain_tool"},
            annotations=WRITE_IDEMPOTENT,
        )
        @mcp_perm(resource=ent["resource"], action="03")
        @_annotate({"data_list": _list_of(data_cls)})
        async def _add_batch(data_list, db_name: str = "default") -> UtilResponse[dict[str, Any]]:
            """批量添加"""
            try:
                _check_batch_size(data_list)
                return await AddHandler().handle_batch(model, data_list, db_name)
            except ToolError as e:
                # 业务失败（超限/关联未找到等）→ 业务失败响应，避免 500 化
                return _tool_error_response(e)

        return _add_batch

    @tool(
        name=name,
        title=f"添加{label}",
        description=f"添加单条{label}记录",
        tags={"domain_tool"},
        annotations=WRITE_IDEMPOTENT,
    )
    @mcp_perm(resource=ent["resource"], action="03")
    @_annotate({"data": data_cls})
    async def _add_single(data, db_name: str = "default") -> UtilResponse[dict[str, Any]]:
        """添加单条记录"""
        try:
            return await AddHandler().handle(model, data, db_name)
        except ToolError as e:
            # 业务失败（如关联记录未找到等）→ 业务失败响应，避免 500 化
            return _tool_error_response(e, data={"id": None})

    return _add_single


def _make_update_tool(ent: dict[str, Any], batch: bool) -> Any:
    """生成单条/批量更新工具函数。"""
    from service_mcp.auth.decorator import mcp_perm
    from service_mcp.handlers.update_handlers import UpdateHandler

    model: type[Base] = ent["model"]
    data_cls = ent["update"]
    name = f"update_{ent['plural'] if batch else ent['name']}"
    label = ent["label"]

    if batch:

        @tool(
            name=name,
            title=f"批量更新{label}",
            description=f"批量更新多条{label}记录，需提供 ids 与 data_list",
            tags={"domain_tool"},
            annotations=WRITE_MUTATING,
        )
        @mcp_perm(resource=ent["resource"], action="04")
        @_annotate({"data_list": _list_of(data_cls)})
        async def _update_batch(
            ids: list[int],
            data_list,
            db_name: str = "default",
        ) -> UtilResponse[dict[str, Any]]:
            """批量更新"""
            try:
                _check_batch_size(data_list)
                return await UpdateHandler().handle_batch(model, ids, data_list, db_name)
            except ToolError as e:
                return _tool_error_response(e)

        return _update_batch

    @tool(
        name=name,
        title=f"更新{label}",
        description=f"更新单条{label}记录，通过 record_id 定位",
        tags={"domain_tool"},
        annotations=WRITE_MUTATING,
    )
    @mcp_perm(resource=ent["resource"], action="04")
    @_annotate({"data": data_cls})
    async def _update_single(
        data,
        record_id: int | None = None,
        db_name: str = "default",
    ) -> UtilResponse[dict[str, int]]:
        """更新单条记录"""
        try:
            return await UpdateHandler().handle(model, data, record_id, db_name)
        except ToolError as e:
            return _tool_error_response(e)

    return _update_single


def _make_delete_tool(ent: dict[str, Any], batch: bool) -> Any:
    """生成单条/批量删除工具函数。"""
    from service_mcp.auth.decorator import mcp_perm
    from service_mcp.handlers.delete_handlers import DeleteHandler

    model: type[Base] = ent["model"]
    data_cls = ent["delete"]
    name = f"delete_{ent['plural'] if batch else ent['name']}"
    label = ent["label"]
    lookup = ent["delete_lookup"]

    if batch:

        @tool(
            name=name,
            title=f"批量删除{label}",
            description=f"批量删除多条{label}记录，每条记录支持{lookup}",
            tags={"domain_tool"},
            annotations=WRITE_DESTRUCTIVE,
        )
        @mcp_perm(resource=ent["resource"], action="06")
        @_annotate({"data_list": _list_of(data_cls)})
        async def _delete_batch(
            data_list, db_name: str = "default"
        ) -> UtilResponse[dict[str, Any]]:
            """批量删除"""
            try:
                _check_batch_size(data_list)
                return await DeleteHandler().handle_batch(model, data_list, db_name)
            except ToolError as e:
                return _tool_error_response(e)

        return _delete_batch

    @tool(
        name=name,
        title=f"删除{label}",
        description=f"删除单条{label}记录，{lookup}",
        tags={"domain_tool"},
        annotations=WRITE_DESTRUCTIVE,
    )
    @mcp_perm(resource=ent["resource"], action="06")
    @_annotate({"data": data_cls})
    async def _delete_single(data, db_name: str = "default") -> UtilResponse[dict[str, int]]:
        """删除单条记录"""
        try:
            return await DeleteHandler().handle(model, data, db_name)
        except ToolError as e:
            return _tool_error_response(e, data={"deleted": 0})

    return _delete_single


def register_crud_tools(module_globals: dict[str, Any]) -> list[str]:
    """根据注册表生成全部 CRUD 工具并注入模块命名空间。

    Args:
        module_globals: 调用方模块的 globals()，工具函数注入其中。

    Returns:
        生成的工具函数名列表（用于 __all__）。
    """
    names: list[str] = []
    for ent in _ENTITIES:
        if ent["create"]:
            for batch in (False, True):
                fn = _make_add_tool(ent, batch)
                tool_name = f"add_{ent['plural'] if batch else ent['name']}"
                module_globals[tool_name] = fn
                names.append(tool_name)
        if ent["update"]:
            for batch in (False, True):
                fn = _make_update_tool(ent, batch)
                tool_name = f"update_{ent['plural'] if batch else ent['name']}"
                module_globals[tool_name] = fn
                names.append(tool_name)
        if ent["delete"]:
            for batch in (False, True):
                fn = _make_delete_tool(ent, batch)
                tool_name = f"delete_{ent['plural'] if batch else ent['name']}"
                module_globals[tool_name] = fn
                names.append(tool_name)
    return names
