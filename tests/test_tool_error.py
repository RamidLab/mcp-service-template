"""ToolError 业务失败收口与 ToolAnnotations 预设接线测试。

覆盖：批量上限收口、定位失败的 RECORD_NOT_FOUND 业务响应（不抛异常、不 500 化）、
CRUD/配置工具的 annotations 元数据。
"""

from fastmcp.decorators import get_fastmcp_meta

from service_mcp.models.pydantic.product import ProductCreate, ProductDelete
from service_mcp.tools import crud_tools
from service_mcp.tools.annotations import (
    READ_ONLY,
    WRITE_DESTRUCTIVE,
    WRITE_IDEMPOTENT,
    WRITE_MUTATING,
)
from service_mcp.tools.basic_tools import health
from service_mcp.tools.crud_factory import MAX_BATCH_SIZE
from service_mcp.utils.enums import Errcode


async def test_batch_cap_business_response(handler_db):
    data = [
        ProductCreate(product_code=f"CAP{i}", product_name=f"超上限{i}")
        for i in range(MAX_BATCH_SIZE + 1)
    ]
    resp = await crud_tools.add_products(data_list=data, db_name="handler_test")
    assert resp.code == Errcode.BUSINESS_FAILED
    assert "超过上限" in resp.message
    assert resp.data is None or resp.data == {}


async def test_delete_not_found_business_response(handler_db):
    resp = await crud_tools.delete_product(
        data=ProductDelete(product_code="NOT_EXIST"), db_name="handler_test"
    )
    assert resp.code == Errcode.RECORD_NOT_FOUND
    assert "NOT_EXIST" in resp.message


def test_tool_annotations_wired():
    assert get_fastmcp_meta(crud_tools.add_product).annotations == WRITE_IDEMPOTENT
    assert get_fastmcp_meta(crud_tools.add_products).annotations == WRITE_IDEMPOTENT
    assert get_fastmcp_meta(crud_tools.update_product).annotations == WRITE_MUTATING
    assert get_fastmcp_meta(crud_tools.delete_products).annotations == WRITE_DESTRUCTIVE
    assert get_fastmcp_meta(health).annotations == READ_ONLY
    assert READ_ONLY.readOnlyHint is True
    assert WRITE_DESTRUCTIVE.destructiveHint is True
