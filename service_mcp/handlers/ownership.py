"""归属档位的写侧判据（这次新增允许落在哪一档、落在谁名下）。

读侧唯一权威是 ``auth.context.scope_visibility_where``；本模块**不另立一套可见性规则**：
只判"调用者有没有资格把这一批数据落在所要的档位上"，整行可写与否仍复用读侧那一份条件
（见 ``base_handlers._visibility_conditions``）。

档位词表用 ``data_scope`` 字符串（platform/team/personal），与 ``DataScope`` 同型；
判据只在带 ``data_scope`` 列的模型上生效——与归属注入段同一口径，没有归属列的示例域不受扰动。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from service_mcp.error.exceptions import ToolError
from service_mcp.models.orm.base import Base
from service_mcp.utils.enums import AuthAction, DataScope, Errcode


if TYPE_CHECKING:
    from service_mcp.auth.context import AuthContext


#: 表名 → 该实体的资源码（两位，与 ``@mcp_perm`` / crud 注册表的 resource 同口径）。
#: 登记了哪个实体，"平台档新增需治理码"这条才对它开口；完整码按
#: ``{前缀}{系统位}{资源码}{治理操作码}`` 现场拼装，这里不写死权限码字面量——
#: 前缀由 ``auth.decorator`` 一处持有，两处不会分叉。
#: 模板示例域（product / product_price）没有 ``data_scope`` 列，档位强制对它们无从谈起，
#: 故这张表留空；下游给实体补上归属列后在此登记，如 ``{"product": "01"}``。
#: 未登记的实体并非放行：平台档只剩超管写得（见 assert_add_allowed 里那条分支）。
GOVERNANCE_RESOURCES: dict[str, str] = {}

#: 档位词表（值域判据用；读侧只认这几个字面量，本表与之同源）
_SCOPE_VALUES = {s.value for s in DataScope}


def governance_code(model: type[Base]) -> str | None:
    """该实体的治理权限码；未登记资源码的实体返回 None（无治理入口）。"""
    from service_mcp.auth.decorator import build_perm_code  # 延迟导入：auth 包顶层会绕回 handlers

    resource = GOVERNANCE_RESOURCES.get(getattr(model, "__tablename__", ""))
    if resource is None:
        return None
    return build_perm_code(resource, AuthAction.Govern.value)


def holds_governance_code(model: type[Base], ctx: AuthContext | None) -> bool:
    """调用者是否持有该实体的治理码。

    超管一律视为持有（不必逐实体再发一次码），**与实体是否登记资源码无关**——未登记的实体
    只是"没人能被下放"，不是"连超管也写不了"。
    """
    if ctx is None:
        return False
    if ctx.is_superuser:
        return True
    code = governance_code(model)
    return code is not None and code in (ctx.permissions or {})


async def assert_add_allowed(model: type[Base], raws: list[dict[str, Any]]) -> None:
    """校验本批新增的归属落点。不合法直接抛 ``ToolError``（整批拒绝，不部分成功）。

    四条判据（按代码里的先后：先验值域，再判三条档位规则）：
      1. ``data_scope`` 只认 ``DataScope`` 的几个取值；不认识的档位（大小写不对、旧词表、
         空串）直接拒绝——这不是越权而是值不合法，且列是裸字符串无 CHECK 约束、读侧只认
         字面量，放过去就是"写得进、谁都读不到"；
      2. 落 ``platform`` 需要该实体的治理码 —— 平台档是全员共用的，不是"谁都能写公共区"；
         实体未登记治理码时只有超管写得；
      3. ``team`` 档的 ``team_id`` 默认只能是调用者自己的部门，持该实体治理码者可跨部门落档
         （判据用治理码，不借读侧的"看得见全部部门"——看得见不等于有权挂）；
      4. ``personal`` 档的 ``owner_id`` 只能是调用者本人。

    ``data_scope`` 为 ``None``（没显式给档）是合法输入、不在值域校验内：落哪一档由归属注入段
    按调用身份决定，本函数只校验"将要落库的那个值"。

    调用位置在通用新增路径的归属注入**之后**：那时 ``data_scope`` / ``team_id`` / ``owner_id``
    才是本批将要落库的真值，默认档（带身份→personal）与显式档走同一条判据。

    无鉴权上下文（tool 模式/后台任务）不校验，模型没有 ``data_scope`` 列同样不校验——
    与读侧"无身份即全量"同口径，但这条**不能被当成安全边界**（admin 模式缺身份是 fail-closed
    拒绝，见 ``auth.decorator``）。

    Args:
        model: 目标 ORM 模型类。
        raws: 已完成归属注入的待写记录字典列表。

    Raises:
        ToolError: 档位值不在 ``DataScope`` 词表内（``Errcode.TOOL_INVALID_PARAMS``，值不合法），
            或归属落点越权（``Errcode.AUTH_INSUFFICIENT_SCOPE``）——两种都是业务可预期失败，
            不是系统错误。
    """
    from service_mcp.auth.context import get_auth_context  # 延迟导入：auth 包顶层会绕回 handlers

    ctx = get_auth_context()
    if ctx is None or not hasattr(model, "data_scope"):
        return

    table = model.__tablename__
    # 治理码持有与否只看模型与身份，与本批行数无关：算一次，两处分支共用
    is_holder = holds_governance_code(model, ctx)
    for raw in raws:
        scope = raw.get("data_scope")
        if scope is not None and scope not in _SCOPE_VALUES:
            # 档位列是裸 String、无 CHECK 约束，读侧只认那几个字面量：
            # 放过不认识的值，写进去的行谁都读不到——静默消失比报错更难查
            raise ToolError(
                f"{table} 的 data_scope 取值无法识别：{scope!r}。"
                f"档位只认 {'/'.join(s.value for s in DataScope)}；"
                "不指定档位请传 None 或省略该字段（由归属注入段按调用身份定默认档）",
                code=Errcode.TOOL_INVALID_PARAMS,
            )
        if scope == DataScope.Platform.value and not is_holder:
            code = governance_code(model)
            if code is None:
                raise ToolError(
                    f"无权在 {table} 新建平台档：该实体未登记治理权限码，"
                    "平台档目前只能由超级管理员写入；需要下放请先在 "
                    "handlers/ownership.GOVERNANCE_RESOURCES 登记该实体的资源码",
                    code=Errcode.AUTH_INSUFFICIENT_SCOPE,
                )
            raise ToolError(
                f"无权在 {table} 新建平台档：平台档是全员共用的内容，"
                f"需要该实体的治理权限码 {code}",
                code=Errcode.AUTH_INSUFFICIENT_SCOPE,
            )
        if scope == DataScope.Team.value:
            team_id = raw.get("team_id")
            if team_id is not None and team_id not in (ctx.team_ids or []) and not is_holder:
                raise ToolError(
                    f"无权在 {table} 把 team 档落到 team_id={team_id}：默认只能落在本部门"
                    f"（{ctx.team_ids or '当前身份无部门'}），跨部门落档需要该实体的治理权限码",
                    code=Errcode.AUTH_INSUFFICIENT_SCOPE,
                )
        if scope == DataScope.Personal.value:
            owner = raw.get("owner_id")
            if owner is not None and owner != ctx.user_id:
                raise ToolError(
                    f"无权在 {table} 把 personal 档挂到 owner_id={owner} 名下："
                    "个人档只对本人可见，只能挂调用者自己（"
                    f"{ctx.user_id}）",
                    code=Errcode.AUTH_INSUFFICIENT_SCOPE,
                )
