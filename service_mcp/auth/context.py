from __future__ import annotations

import contextvars
from dataclasses import dataclass, field


@dataclass
class PermScope:
    data_scope: str = "ALL"
    custom: list[dict] = field(default_factory=list)


@dataclass
class AuthContext:
    user_id: int = 0
    username: str = ""
    roles: list[str] = field(default_factory=list)
    permissions: dict[str, PermScope] = field(default_factory=dict)
    is_superuser: bool = False
    is_staff: bool = False
    access_token: str | None = None  # JWT token，用于调用后端 API
    team_ids: list[int] = field(default_factory=list)  # 用户所属部门（团队）ID 列表（首个为自属部门）


_auth_context: contextvars.ContextVar[AuthContext | None] = contextvars.ContextVar(
    "auth_context", default=None
)
_current_perm_scope: contextvars.ContextVar[PermScope | None] = contextvars.ContextVar(
    "current_perm_scope", default=None
)


def get_auth_context() -> AuthContext | None:
    return _auth_context.get()


def set_auth_context(ctx: AuthContext | None) -> None:
    """注入/清除当前请求的认证上下文（测试与包模式宿主使用）。"""
    _auth_context.set(ctx)


def get_current_scope() -> PermScope | None:
    return _current_perm_scope.get()


def current_owner() -> int | None:
    """当前操作者归属：admin 模式取后端用户 ID；无鉴权（tool）返回 None。"""
    ctx = _auth_context.get()
    if ctx is None:
        return None
    return ctx.user_id


def visible_owners() -> set[int] | None:
    """【旧两态口径】当前可见的归属集合；None 表示全量可见。

    - 无鉴权调用：全量（None，不隔离）
    - 普通用户：仅自己的数据（{user_id}）
    - superuser：全量

    模型带 ``data_scope`` 列时请改用 :func:`scope_visibility_where`（三级数据范围）。
    """
    ctx = _auth_context.get()
    if ctx is None or ctx.is_superuser:
        return None
    return {ctx.user_id}


def current_team_id() -> int | None:
    """当前操作者的自属部门 ID：``team_ids`` 首个元素；无鉴权/无部门返回 None。

    ``team_ids`` 由认证来源按部门树下发，约定首个元素即用户自属部门（其后为下级部门），
    故取首个作为团队档写入时的默认归属；该约定与可见性 team 分支读同一份 ``team_ids``，
    不另立来源。无部门时返回 None——调用方不得据此臆造部门，也不得擅自改动数据档位。
    """
    ctx = _auth_context.get()
    if ctx is None or not ctx.team_ids:
        return None
    return ctx.team_ids[0]


def scope_visibility_where(model) -> list | None:
    """三级数据范围可见性条件（平台 / 部门 / 个人），服务端强制过滤。

    规则：
      - 无鉴权（tool 模式）：全量可见（None，供采集/后台使用）
      - platform：所有登录用户可见
      - team：部门成员（team_ids 命中）可见；创始管理员（superuser）可见全部部门
      - personal：仅 owner 本人可见 —— 创始管理员也不可见（安全底线）

    team 分支以模型自身的 ``team_id`` 为部门判据列：模型没有该列时该档**不参与**条件
    构造（既不抛异常，也不放宽其它档），与本函数仅认 ``data_scope`` 列的既有降级口径一致。

    数据发布审核：模型带 ``publish_status`` 列时，PENDING/REJECTED（未审核/已拒绝）
    仅归属者本人可见，APPROVED（含旧数据 NULL）才按 data_scope 正常可见。

    Args:
        model: 带 data_scope/owner_id 列的 ORM 模型；team 档另需 team_id 列。

    Returns:
        SQLAlchemy 条件列表；模型无 data_scope 列时返回 None（调用方回落旧口径）。
    """
    if not hasattr(model, "data_scope"):
        return None
    from sqlalchemy import and_, or_

    from service_mcp.utils.enums import DataScope

    ctx = _auth_context.get()
    if ctx is None:
        return None

    scope_col = model.data_scope
    owner_col = model.owner_id

    # 数据发布审核：PENDING/REJECTED（未审核/已拒绝）仅归属者本人可见，
    # APPROVED 才按 data_scope 正常可见（平台数据审核通过前不公开）。
    if hasattr(model, "publish_status"):
        from service_mcp.utils.enums import PublishStatus

        # NULL 视为已审核（旧数据无该列值），仅显式 PENDING/REJECTED 被门槛拦截
        approved = or_(
            model.publish_status == PublishStatus.Approved.value,
            model.publish_status.is_(None),
        )
        unpublished = or_(
            model.publish_status == PublishStatus.Pending.value,
            model.publish_status == PublishStatus.Rejected.value,
        )
        # 未审核/已拒绝：仅归属者；已审核（含旧数据 NULL）按 scope
        owner_scope = and_(unpublished, owner_col == ctx.user_id)
    else:
        approved = True
        owner_scope = False

    # 兼容迁移前的旧数据：data_scope 为 NULL 时按 owner 推断（NULL→平台，有值→个人）
    platform_cond = and_(
        or_(
            scope_col == DataScope.Platform.value,
            and_(scope_col.is_(None), owner_col.is_(None)),
        ),
        approved,
    )
    personal_cond = and_(
        or_(
            scope_col == DataScope.Personal.value,
            and_(scope_col.is_(None), owner_col.isnot(None)),
        ),
        owner_col == ctx.user_id,
    )
    conds: list = [platform_cond, personal_cond]
    if owner_scope is not False:
        conds.append(owner_scope)

    # team 档：判据列是模型自身的 team_id（部门）。无该列时该档不参与条件（不抛异常、
    # 也不放宽其它档）——与「模型无 data_scope 列→不过滤」同样的存在性探测口径。
    # 部门树命中用同一个 ctx.team_ids；superuser 见全部部门的已发布 team 数据。
    if hasattr(model, "team_id"):
        if ctx.is_superuser:
            conds.append(and_(scope_col == DataScope.Team.value, approved))
        elif ctx.team_ids:
            conds.append(
                and_(
                    scope_col == DataScope.Team.value,
                    model.team_id.in_(ctx.team_ids),
                    approved,
                )
            )

    return [or_(*conds)]