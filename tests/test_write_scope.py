"""写侧三级数据范围校验与归属注入测试。

读侧（`auth.context.scope_visibility_where`）早已按 data_scope/owner_id/team_id 收敛可见性，
写侧此前完全不接这套口径：`_resolve_record_id` 只按主键定位，任何持有更新/删除权限码的
调用方都能改他人 personal 行；新增也不落归属，`current_team_id()` 因此是死代码。
本文件把两侧钉成同一份规则，并保住 tool 模式（无鉴权上下文）的既有全量口径。
"""

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from service_mcp.auth.context import AuthContext, _auth_context
from service_mcp.error.exceptions import ToolError
from service_mcp.handlers.add_handlers import AddHandler
from service_mcp.handlers.delete_handlers import DeleteHandler
from service_mcp.handlers.update_handlers import UpdateHandler
from service_mcp.models.pydantic import BaseDeleteModel
from service_mcp.utils.enums import DataScope, Errcode
from tests.conftest import HANDLER_DB_NAME
from tests.test_scope_visibility import ScopeDoc


class DocUpdate(BaseModel):
    """ScopeDoc 的更新载荷（测试用最小模型）。"""

    title: str | None = None


class DocCreate(BaseModel):
    """ScopeDoc 的新增载荷：归属列刻意不出现，由写侧按身份注入。"""

    title: str


class DocDelete(BaseDeleteModel):
    """ScopeDoc 的删除载荷：按主键定位。"""


@pytest.fixture(autouse=True)
def _clear_auth_context():
    """每条用例后清空身份，避免上下文泄漏到其它测试。"""
    yield
    _auth_context.set(None)


def _login_as(user_id: int, team_ids: list[int] | None = None) -> None:
    """以普通用户身份注入上下文（非 superuser：个人档仅本人可见）。"""
    _auth_context.set(AuthContext(user_id=user_id, username=f"u{user_id}", team_ids=team_ids or []))


async def _fetch_doc(handler_db, doc_id: int) -> ScopeDoc:
    async with handler_db.get_session() as session:
        obj = (await session.execute(select(ScopeDoc).where(ScopeDoc.id == doc_id))).scalar_one()
    return obj


async def test_update_others_personal_row_is_rejected(handler_db):
    """他人 personal 行：按 id 更新必须失败，且不披露它是否存在。"""
    other = await handler_db.insert(
        ScopeDoc(title="p-other", data_scope=DataScope.Personal.value, owner_id=11)
    )
    _login_as(10)

    with pytest.raises(ToolError) as exc:
        await UpdateHandler().handle(ScopeDoc, DocUpdate(title="越权改名"), other.id, HANDLER_DB_NAME)

    assert exc.value.code == Errcode.RECORD_NOT_FOUND
    assert "越权改名" not in str(exc.value)
    assert "不可见" not in str(exc.value)
    assert (await _fetch_doc(handler_db, other.id)).title == "p-other"


async def test_update_own_personal_row_succeeds(handler_db):
    """本人 personal 行放行——证明上一条不是把写侧一刀切关掉。"""
    mine = await handler_db.insert(
        ScopeDoc(title="p-mine", data_scope=DataScope.Personal.value, owner_id=10)
    )
    _login_as(10)

    resp = await UpdateHandler().handle(ScopeDoc, DocUpdate(title="自己改"), mine.id, HANDLER_DB_NAME)

    assert resp.code == Errcode.SUCCESS
    assert (await _fetch_doc(handler_db, mine.id)).title == "自己改"


async def test_delete_others_personal_row_is_rejected(handler_db):
    """删除与更新共用同一条定位口径。"""
    other = await handler_db.insert(
        ScopeDoc(title="p-other", data_scope=DataScope.Personal.value, owner_id=11)
    )
    _login_as(10)

    with pytest.raises(ToolError) as exc:
        await DeleteHandler().handle(ScopeDoc, DocDelete(record_id=other.id), HANDLER_DB_NAME)

    assert exc.value.code == Errcode.RECORD_NOT_FOUND


async def test_update_batch_only_touches_visible_rows(handler_db):
    """批量更新按 id 直写、绕过单条定位，必须单独收敛。

    他人行不写入；返回的 count 只算可见部分；提示里不区分"不存在/不可见"，
    否则批量接口就成了探测他人行是否存在的信道。
    """
    mine = await handler_db.insert(
        ScopeDoc(title="p-mine", data_scope=DataScope.Personal.value, owner_id=10)
    )
    other = await handler_db.insert(
        ScopeDoc(title="p-other", data_scope=DataScope.Personal.value, owner_id=11)
    )
    _login_as(10)

    resp = await UpdateHandler().handle_batch(
        ScopeDoc,
        [mine.id, other.id],
        [DocUpdate(title="改A"), DocUpdate(title="改B")],
        HANDLER_DB_NAME,
    )

    assert resp.data["count"] == 1
    assert resp.data["ids"] == [mine.id]
    assert "不可见" not in resp.message
    assert "他人" not in resp.message
    assert (await _fetch_doc(handler_db, mine.id)).title == "改A"
    assert (await _fetch_doc(handler_db, other.id)).title == "p-other"


async def test_write_without_context_keeps_full_access(handler_db):
    """tool 模式（无 AuthContext）不收敛：采集/后台任务照旧可写任意行。"""
    row = await handler_db.insert(
        ScopeDoc(title="bg", data_scope=DataScope.Personal.value, owner_id=11)
    )

    resp = await UpdateHandler().handle(ScopeDoc, DocUpdate(title="后台改写"), row.id, HANDLER_DB_NAME)

    assert resp.code == Errcode.SUCCESS
    assert (await _fetch_doc(handler_db, row.id)).title == "后台改写"


async def test_add_stamps_owner_for_personal_default(handler_db):
    """有身份且未表态档位：新增落 personal + 当前用户（最小权限）。"""
    _login_as(10, team_ids=[3])

    resp = await AddHandler().handle(ScopeDoc, DocCreate(title="新建"), HANDLER_DB_NAME)

    assert resp.code == Errcode.SUCCESS
    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.data_scope == DataScope.Personal.value
    assert obj.owner_id == 10


async def test_add_keeps_explicit_platform_scope(handler_db):
    """显式表态平台档：不被默认注入改写。"""
    _login_as(10)

    class DocCreatePlatform(DocCreate):
        data_scope: str = DataScope.Platform.value

    resp = await AddHandler().handle(
        ScopeDoc, DocCreatePlatform(title="平台共享"), HANDLER_DB_NAME
    )

    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.data_scope == DataScope.Platform.value


async def test_add_without_context_does_not_stamp(handler_db):
    """无身份：不注入归属、不擅自改档位（保持 tool 模式现状）。"""
    resp = await AddHandler().handle(ScopeDoc, DocCreate(title="裸建"), HANDLER_DB_NAME)

    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.owner_id is None
    assert obj.data_scope is None
