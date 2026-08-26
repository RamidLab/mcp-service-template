"""测试 CSV 导出（utils/export.py + tools/export_tools.py）"""

from datetime import date

from service_mcp.models.common import UtilResponse
from service_mcp.tools.export_tools import export_products_csv
from service_mcp.utils.export import csv_bom, rows_to_csv


def test_csv_bom():
    assert csv_bom() == chr(0xFEFF)


def test_rows_to_csv_basic():
    text = rows_to_csv(
        ["id", "name", "launch_date", "note"],
        [[1, "产品A", date(2026, 1, 2), None], [2, "产品B", None, "x"]],
    )
    lines = text.splitlines()
    assert lines[0].startswith(chr(0xFEFF))
    assert lines[0].lstrip(chr(0xFEFF)) == "id,name,launch_date,note"
    assert lines[1] == "1,产品A,2026-01-02,"
    assert lines[2] == "2,产品B,,x"


async def test_export_products_csv_tool(handler_db, seeded_product):
    resp: UtilResponse[str] = await export_products_csv(db_name="handler_test")
    assert resp.code == 0
    text = resp.data
    assert text is not None
    assert text.startswith(chr(0xFEFF))
    # 表头 + 数据行
    assert "product_code" in text
    assert "P0001" in text
    # 枚举渲染为中文 label
    assert "权益类" in text
    assert "手动导入" in text


async def test_export_products_csv_filter(handler_db, seeded_product):
    # 过滤条件不命中 → 空数据（仅表头）
    resp = await export_products_csv(product_code="NOPE", db_name="handler_test")
    assert resp.code == 0
    text = resp.data or ""
    lines = text.strip().splitlines()
    assert len(lines) == 1
