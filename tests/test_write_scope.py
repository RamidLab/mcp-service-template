"""写侧三级数据范围校验与归属注入测试。

读侧（`auth.context.scope_visibility_where`）早已按 data_scope/owner_id/team_id 收敛可见性，
写侧此前完全不接这套口径：`_resolve_record_id` 只按主键定位，任何持有更新/删除权限码的
调用方都能改他人 personal 行；新增也不落归属，`current_team_id()` 因此是死代码。
本文件把两侧钉成同一份规则，并保住 tool 模式（无鉴权上下文）的既有全量口径。

归属档位这一侧还钉住四条判据（`handlers/ownership.py`）：档位值只认词表内的三个、
平台档需该实体的治理权限码、personal 只能挂本人、team 只能落本部门。
"""

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select

from service_mcp.auth.context import AuthContext, PermScope, _auth_context
from service_mcp.auth.discovery import get_all_permissions
from service_mcp.error.exceptions import ToolError
from service_mcp.handlers import ownership
from service_mcp.handlers.add_handlers import AddHandler
from service_mcp.handlers.delete_handlers import DeleteHandler
from service_mcp.handlers.update_handlers import UpdateHandler
from service_mcp.models.pydantic import BaseDeleteModel
from service_mcp.utils.enums import AuthAction, DataScope, Errcode
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


class DocCreatePlatform(DocCreate):
    """显式表态平台档的新增载荷（自封平台档的那条路径就用它）。"""

    data_scope: str = DataScope.Platform.value


@pytest.fixture(autouse=True)
def _clear_auth_context():
    """每条用例后清空身份，避免上下文泄漏到其它测试。"""
    yield
    _auth_context.set(None)


def _login_as(
    user_id: int,
    team_ids: list[int] | None = None,
    *,
    permissions: dict[str, PermScope] | None = None,
    superuser: bool = False,
) -> None:
    """注入身份（默认非 superuser、无权限码：个人档仅本人可见、平台档不可写）。"""
    _auth_context.set(
        AuthContext(
            user_id=user_id,
            username=f"u{user_id}",
            team_ids=team_ids or [],
            permissions=permissions or {},
            is_superuser=superuser,
        )
    )


@pytest.fixture
def govern_registry() -> str:
    """把测试模型登记进治理注册表（表名 → 资源码），返回该实体的治理权限码。

    码不写死字面量：由前缀 + 资源码 + 治理操作码现场拼装，与 `@mcp_perm` 同一份格式。
    """
    resource = "07"
    ownership.GOVERNANCE_RESOURCES[ScopeDoc.__tablename__] = resource
    yield f"SM_01{resource}{AuthAction.Govern.value}"
    ownership.GOVERNANCE_RESOURCES.pop(ScopeDoc.__tablename__, None)


async def _fetch_doc(handler_db, doc_id: int) -> ScopeDoc:
    async with handler_db.get_session() as session:
        obj = (await session.execute(select(ScopeDoc).where(ScopeDoc.id == doc_id))).scalar_one()
    return obj


async def _doc_count(handler_db) -> int:
    async with handler_db.get_session() as session:
        return int((await session.execute(select(func.count()).select_from(ScopeDoc))).scalar_one())


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


async def test_add_keeps_explicit_platform_scope(govern_registry, handler_db):
    """显式表态平台档（持该实体治理码）：不被默认注入改写。"""
    _login_as(10, permissions={govern_registry: PermScope()})

    resp = await AddHandler().handle(
        ScopeDoc, DocCreatePlatform(title="平台共享"), HANDLER_DB_NAME
    )

    assert resp.code == Errcode.SUCCESS
    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.data_scope == DataScope.Platform.value


async def test_add_without_context_does_not_stamp(handler_db):
    """无身份：不注入归属、不擅自改档位（保持 tool 模式现状）。"""
    resp = await AddHandler().handle(ScopeDoc, DocCreate(title="裸建"), HANDLER_DB_NAME)

    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.owner_id is None
    assert obj.data_scope is None


# ── 归属档位判据 ──


async def test_unknown_scope_literal_is_rejected(govern_registry, handler_db):
    """不认识的档位值一律拒写：档位列是裸字符串、无 CHECK 约束，读侧只认词表里那几个字面量，
    放过去就是"写得进、谁都读不到"。"""
    _login_as(10)
    for bad in ("Platform", "PERSONAL", "public", ""):

        class DocCreateBad(DocCreate):
            data_scope: str = bad

        resp = await AddHandler().handle(ScopeDoc, DocCreateBad(title="坏档"), HANDLER_DB_NAME)

        assert resp.code == Errcode.TOOL_INVALID_PARAMS, bad
    assert await _doc_count(handler_db) == 0


async def test_assert_add_allowed_rejects_unknown_tier(govern_registry):
    """经新增路径时值域已挡；这条钉**直接拼行的调用者**那条路（治理工具/后续任务）。"""
    _login_as(10)
    for bad in ("Platform", "PERSONAL", "public", ""):
        with pytest.raises(ToolError) as exc:
            await ownership.assert_add_allowed(ScopeDoc, [{"data_scope": bad}])
        assert exc.value.code == Errcode.TOOL_INVALID_PARAMS, f"{bad!r} 应被当成非法档位值"
    # None（没显式给档）不是非法值——落哪一档由归属注入段按身份决定
    await ownership.assert_add_allowed(ScopeDoc, [{"data_scope": None}])


async def test_self_claimed_platform_scope_is_rejected(govern_registry, handler_db):
    """普通登录用户自封平台档必须被拒：平台档是全员共用的档位，不是"谁都能写公共区"。"""
    _login_as(10)

    resp = await AddHandler().handle(
        ScopeDoc, DocCreatePlatform(title="自封平台"), HANDLER_DB_NAME
    )

    assert resp.code == Errcode.AUTH_INSUFFICIENT_SCOPE
    assert resp.data["id"] is None
    assert await _doc_count(handler_db) == 0


async def test_platform_scope_allowed_for_superuser(handler_db):
    """超管视为持有治理码，不必逐实体再发一次码。"""
    _login_as(1, superuser=True)

    resp = await AddHandler().handle(
        ScopeDoc, DocCreatePlatform(title="超管平台档"), HANDLER_DB_NAME
    )

    assert resp.code == Errcode.SUCCESS
    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.data_scope == DataScope.Platform.value


async def test_platform_scope_on_unregistered_entity_is_superuser_only(handler_db):
    """未登记治理码的实体：平台档只剩超管写得——宁可挡住，也不给一把不存在的码放行。"""
    _login_as(10)

    resp = await AddHandler().handle(
        ScopeDoc, DocCreatePlatform(title="未登记实体自封平台"), HANDLER_DB_NAME
    )

    assert resp.code == Errcode.AUTH_INSUFFICIENT_SCOPE
    assert "未登记" in resp.message
    assert await _doc_count(handler_db) == 0


async def test_personal_scope_cannot_name_another_owner(handler_db):
    """personal 档只能挂调用者自己：个人档只对本人可见，挂他人名下等于替别人建私有数据。"""
    _login_as(10)

    class DocCreateForOther(DocCreate):
        data_scope: str = DataScope.Personal.value
        owner_id: int = 11

    resp = await AddHandler().handle(ScopeDoc, DocCreateForOther(title="挂他人"), HANDLER_DB_NAME)

    assert resp.code == Errcode.AUTH_INSUFFICIENT_SCOPE
    assert await _doc_count(handler_db) == 0


async def test_team_scope_must_be_one_of_caller_departments(handler_db):
    """team 档只能落在身份里的部门；跨部门落档要治理码（看得见全部部门 ≠ 有权挂）。"""
    _login_as(10, team_ids=[3])

    class DocCreateTeam(DocCreate):
        data_scope: str = DataScope.Team.value
        team_id: int = 3

    resp = await AddHandler().handle(ScopeDoc, DocCreateTeam(title="本部门"), HANDLER_DB_NAME)
    assert resp.code == Errcode.SUCCESS

    class DocCreateForeignTeam(DocCreate):
        data_scope: str = DataScope.Team.value
        team_id: int = 9

    before = await _doc_count(handler_db)
    rejected = await AddHandler().handle(
        ScopeDoc, DocCreateForeignTeam(title="他人部门"), HANDLER_DB_NAME
    )

    assert rejected.code == Errcode.AUTH_INSUFFICIENT_SCOPE
    assert await _doc_count(handler_db) == before


async def test_team_scope_cross_department_needs_governance_code(
    govern_registry, handler_db
):
    """同一条跨部门落档，持治理码才放行。"""
    _login_as(10, team_ids=[3], permissions={govern_registry: PermScope()})

    class DocCreateForeignTeam(DocCreate):
        data_scope: str = DataScope.Team.value
        team_id: int = 9

    resp = await AddHandler().handle(
        ScopeDoc, DocCreateForeignTeam(title="治理落他人部门"), HANDLER_DB_NAME
    )

    assert resp.code == Errcode.SUCCESS
    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.team_id == 9


async def test_tier_checks_skipped_without_context(handler_db):
    """无鉴权上下文（tool 模式/后台任务）不做档位判据——与读侧"无身份即全量"同口径。"""
    resp = await AddHandler().handle(
        ScopeDoc, DocCreatePlatform(title="后台建平台档"), HANDLER_DB_NAME
    )

    assert resp.code == Errcode.SUCCESS
    obj = await _fetch_doc(handler_db, resp.data["id"])
    assert obj.data_scope == DataScope.Platform.value


async def test_model_without_scope_column_is_not_checked():
    """没有 data_scope 列的模型不参与档位判据（示例域不受影响）。"""
    from service_mcp.models.orm import Product

    _login_as(10)
    await ownership.assert_add_allowed(Product, [{"name": "无归属列"}])


def test_registered_governance_code_is_discoverable(govern_registry):
    """登记的治理码必须进 /permissions：RBAC 只灌那一枚清单里的码，
    不在清单上就没人能被授予，平台档从此只剩超管写得。"""
    codes = {p["code"] for p in get_all_permissions()}
    assert govern_registry in codes


async def test_admin_mode_without_identity_cannot_write_scoped_row(handler_db, monkeypatch):
    """鉴权开着（admin 模式）却没有身份 ⇒ 带归属列的模型写侧拒绝。

    装饰器那层的 fail-closed 只挡工具调用；直接调 handler（后台任务、进程内宿主）绕得开它，
    所以判据要在写侧再落一次。tool 模式口径不变——见 test_write_without_context_keeps_full_access。
    """
    row = await handler_db.insert(
        ScopeDoc(title="bg", data_scope=DataScope.Personal.value, owner_id=11)
    )
    monkeypatch.setenv("MCP_AUTH_MODE", "admin")
    assert _auth_context.get() is None

    with pytest.raises(ToolError) as exc:
        await UpdateHandler().handle(
            ScopeDoc, DocUpdate(title="无身份改写"), row.id, HANDLER_DB_NAME
        )

    assert exc.value.code == Errcode.AUTH_INSUFFICIENT_SCOPE
    assert "不可见" not in str(exc.value), "拒绝的理由是「没有身份」，不是那行的存在性"


async def test_admin_mode_without_identity_still_writes_unscoped_model(
    handler_db, seeded_product, monkeypatch
):
    """没有归属列的模型不受这条判据影响（示例域/后台采集照常可写）。"""
    from service_mcp.models.orm import Product
    from service_mcp.models.pydantic.product import ProductUpdate

    monkeypatch.setenv("MCP_AUTH_MODE", "admin")
    resp = await UpdateHandler().handle(
        Product, ProductUpdate(name="无身份也写得动"), seeded_product.id, HANDLER_DB_NAME
    )
    assert resp.code == Errcode.SUCCESS


async def test_invisible_and_missing_rows_answer_identically(handler_db):
    """越权与"真没有这一行"必须回同一句话。

    两种答案并存，写接口就成了探测他人行是否存在的信道；而回"不可见"同样是泄露。
    断言先把 id 归一，再逐字比较两句——只要文案分叉就红。
    """
    other = await handler_db.insert(
        ScopeDoc(title="p-other", data_scope=DataScope.Personal.value, owner_id=11)
    )
    missing_id = other.id + 999
    _login_as(10)

    with pytest.raises(ToolError) as invisible:
        await UpdateHandler().handle(
            ScopeDoc, DocUpdate(title="x"), other.id, HANDLER_DB_NAME
        )
    with pytest.raises(ToolError) as absent:
        await UpdateHandler().handle(
            ScopeDoc, DocUpdate(title="x"), missing_id, HANDLER_DB_NAME
        )

    def _normalize(text: str, target: int) -> str:
        return text.replace(f"id={target}", "id=?")

    left = _normalize(str(invisible.value), other.id)
    right = _normalize(str(absent.value), missing_id)
    assert left == right, f"两句答案可分辨，等于给出了一条探测信道：\n{left!r}\n{right!r}"
    assert "不可见" not in left
    # 收敛生效时不得断言"不存在"：那会引导调用者去新建，撞唯一键反而把存在性暴露出来
    assert "不存在，或不在你的数据范围内" in left
    assert invisible.value.code == absent.value.code == Errcode.RECORD_NOT_FOUND
