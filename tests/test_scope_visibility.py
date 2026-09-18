"""三级数据范围可见性与软删隐藏集成测试。

在测试内定义带 data_scope/owner_id/team_id/publish_status 列的临时模型与无归属子表，
针对内存 SQLite 覆盖：平台/部门/个人三级矩阵、发布审核门槛、父可见性（孤儿豁免）、
软删行默认隐藏。无鉴权（tool 模式）不过滤的口径同时验证。
"""

import pytest
from sqlalchemy import Boolean, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

from service_mcp.auth.context import AuthContext, _auth_context
from service_mcp.handlers.query_handlers import QueryHandler
from service_mcp.models.orm import PARENT_ENTITY_MAP, Base
from service_mcp.models.pydantic.filter import ProductFilter
from service_mcp.models.orm import Product
from service_mcp.models.schemas import PaginationParams
from service_mcp.utils.enums import DataScope, PublishStatus


class ScopeDoc(Base):
    """临时模型：带三级归属列 + 发布审核 + 软删列。"""

    __tablename__ = "test_scope_doc"

    title: Mapped[str] = mapped_column(String(50))
    data_scope: Mapped[str | None] = mapped_column(String(20), default=None)
    owner_id: Mapped[int | None] = mapped_column(Integer, default=None)
    team_id: Mapped[int | None] = mapped_column(Integer, default=None)
    publish_status: Mapped[str | None] = mapped_column(String(20), default=None)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class ScopeDocChild(Base):
    """临时子表：无自身归属列，靠父实体可见性过滤。"""

    __tablename__ = "test_scope_doc_child"

    doc_id: Mapped[int | None] = mapped_column(Integer, default=None)
    note: Mapped[str] = mapped_column(String(50))


@pytest.fixture
def child_registry(monkeypatch):
    """把测试子表登记进父可见性注册表。"""
    monkeypatch.setitem(PARENT_ENTITY_MAP, ScopeDocChild, (ScopeDoc, "doc_id"))


@pytest.fixture
async def docs(handler_db):
    """预置覆盖各档位的数据行（user_id=10 / team 3 视角设计）。"""
    rows = {
        "platform": ScopeDoc(title="platform", data_scope=DataScope.Platform.value),
        "team_mine": ScopeDoc(
            title="team-mine",
            data_scope=DataScope.Team.value,
            owner_id=10,
            team_id=3,
        ),
        "team_other": ScopeDoc(
            title="team-other",
            data_scope=DataScope.Team.value,
            owner_id=11,
            team_id=9,
        ),
        "personal_mine": ScopeDoc(
            title="p-mine",
            data_scope=DataScope.Personal.value,
            owner_id=10,
        ),
        "personal_other": ScopeDoc(
            title="p-other",
            data_scope=DataScope.Personal.value,
            owner_id=11,
        ),
        "pending_platform_other": ScopeDoc(
            title="pp-other",
            data_scope=DataScope.Platform.value,
            owner_id=11,
            publish_status=PublishStatus.Pending.value,
        ),
        "pending_mine": ScopeDoc(
            title="pm-mine",
            data_scope=DataScope.Platform.value,
            owner_id=10,
            publish_status=PublishStatus.Pending.value,
        ),
        "legacy_null": ScopeDoc(title="legacy"),
        "soft_deleted": ScopeDoc(
            title="gone",
            data_scope=DataScope.Platform.value,
            is_deleted=True,
        ),
    }
    for r in rows.values():
        await handler_db.insert(r)
    return rows


async def _titles(handler_db, where: list) -> set[str]:
    async with handler_db.get_session() as session:
        res = await session.execute(select(ScopeDoc).where(*where))
        return {r.title for r in res.scalars().all()}


async def _enter(user_id: int, *, teams: list[int] | None = None, superuser: bool = False):
    return _auth_context.set(
        AuthContext(user_id=user_id, username="u", team_ids=teams or [], is_superuser=superuser)
    )


async def test_no_context_returns_none_for_scope():
    """无鉴权上下文（tool 模式）：scope 条件为空，不做过滤（全量语义）。"""
    assert QueryHandler._scope_visibility_where(ScopeDoc) == []


async def test_normal_user_visibility_matrix(handler_db, docs):
    token = await _enter(10, teams=[3])
    try:
        where = QueryHandler._scope_visibility_where(ScopeDoc)
        assert where  # 有上下文必须给出条件
        titles = await _titles(handler_db, where)
        # 软删行由列表路径叠加隐藏（此处 helper 只管归属）
        assert {"platform", "team-mine", "p-mine", "pm-mine", "legacy", "gone"} == titles
        assert "team-other" not in titles
        assert "p-other" not in titles
        assert "pp-other" not in titles  # 未审核平台数据非归属者不可见
    finally:
        _auth_context.reset(token)


async def test_superuser_cannot_see_personal(handler_db, docs):
    token = await _enter(1, superuser=True)
    try:
        titles = await _titles(handler_db, QueryHandler._scope_visibility_where(ScopeDoc))
        assert {"platform", "team-mine", "team-other", "legacy", "gone"} <= titles
        assert "p-other" not in titles
        assert "p-mine" not in titles  # 安全底线：创始管理员也不可见他人 personal
    finally:
        _auth_context.reset(token)


async def test_list_path_hides_soft_deleted(handler_db, docs):
    """完整列表路径：叠加软删隐藏后 gone 不出现。"""
    token = await _enter(10, teams=[3])
    try:
        handler = QueryHandler()
        resp = await handler.handle(
            ScopeDoc,
            PaginationParams(page=1, page_size=200),
            None,
            "handler_test",
        )
        page = resp.data
        assert page is not None
        got = {item["title"] for item in page.items}
        assert "gone" not in got
        assert {"platform", "team-mine", "p-mine"} <= got
    finally:
        _auth_context.reset(token)


async def test_parent_visibility_with_orphan_exempt(handler_db, docs, child_registry):
    """子表按父实体可见过滤：不可见父行被挡，孤儿（外键空/父缺失）豁免。"""
    visible_parent = docs["platform"].id
    hidden_parent = docs["personal_other"].id
    children = [
        ScopeDocChild(doc_id=visible_parent, note="c-visible"),
        ScopeDocChild(doc_id=hidden_parent, note="c-hidden"),
        ScopeDocChild(doc_id=None, note="c-orphan-null"),
        ScopeDocChild(doc_id=999999, note="c-parent-gone"),
    ]
    for c in children:
        await handler_db.insert(c)

    token = await _enter(10, teams=[3])
    try:
        where = QueryHandler._parent_visibility_where(ScopeDocChild)
        assert where
        async with handler_db.get_session() as session:
            res = await session.execute(select(ScopeDocChild).where(*where))
            notes = {r.note for r in res.scalars().all()}
        assert {"c-visible", "c-orphan-null", "c-parent-gone"} == notes
        assert "c-hidden" not in notes
    finally:
        _auth_context.reset(token)


async def test_product_list_unaffected_without_scope_columns(handler_db, seeded_product):
    """无归属列的示例实体：叠加层为 no-op，既有列表行为不变。"""
    token = await _enter(10, teams=[3])
    try:
        resp = await QueryHandler().handle(
            Product,
            PaginationParams(page=1, page_size=200),
            ProductFilter(),
            db_name="handler_test",
        )
        assert resp.data is not None
        assert resp.data.pagination.total == 1
    finally:
        _auth_context.reset(token)