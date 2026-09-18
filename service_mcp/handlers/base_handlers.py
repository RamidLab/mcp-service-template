from datetime import date
from typing import Any, cast

from sqlalchemy import DECIMAL, Date, Integer, String, func, select

from service_mcp.db.core import get_db_manager
from service_mcp.error.exceptions import ToolError, UniqueConflictError
from service_mcp.models.orm import Product
from service_mcp.models.orm.base import Base
from service_mcp.utils.common import to_date_flexible
from service_mcp.utils.enums import AbnormalType, Errcode


async def _get_mgr(db_name: str = "default"):
    """获取数据库管理器实例（快捷方式，兼容旧引用）。"""
    return await get_db_manager(db_name)


def owner_visibility_where(model: type[Base]) -> list | None:
    """当前身份的可见数据条件（查询叠加用）；全量可见 → None。

    模型带 data_scope 列（三级数据范围）时走 scope_visibility_where
    （平台/部门/个人 + 发布审核口径，见 auth.context）；
    仅带 owner 列的模型回退旧两态逻辑（无鉴权/superuser 全量，普通用户仅本人）。
    """
    if hasattr(model, "data_scope"):
        from service_mcp.auth.context import scope_visibility_where  # 延迟导入避免循环引用

        return scope_visibility_where(model)
    if not hasattr(model, "owner"):
        return None
    owner_col = cast(Any, model).owner  # owner 列仅存在于部分模型，Base 无此属性
    from service_mcp.auth.context import visible_owners

    visible = visible_owners()
    if visible is None:
        return None
    return [owner_col.in_(visible)]


def apply_owner_visibility(stmt, model: type[Base], *, prefer_own: bool = False):
    """给定位类查询附加 owner 可见性过滤（record_id/code 定位共用）。

    prefer_own=True：同名多归属时优先定位自己的（自己 > 共享池）。
    """
    owner_where = owner_visibility_where(model)
    if owner_where:
        stmt = stmt.where(*owner_where)
        if prefer_own:
            # 归属列两种口径都可能：旧两态用 owner，三级范围用 owner_id
            owner_col = getattr(model, "owner", None)
            if owner_col is None:
                owner_col = getattr(model, "owner_id", None)
            if owner_col is not None:
                from service_mcp.auth.context import current_owner

                stmt = stmt.order_by(owner_col == current_owner())
    return stmt


class CodeResolveMixin:
    """
    提供外键 code → id 解析和名称 → id 兜底解析的共享逻辑。

    该 Mixin 用于 AddHandler、UpdateHandler 和 DeleteHandler，避免解析逻辑重复。

    工作机制：
        - code 解析：当请求数据中包含业务编码（如 ``product_code``）时，
          通过数据库查询将其转换为对应记录的主键 ID，并移除原始 code 字段。
        - 名称解析：当 code 未提供但给出了可读名称时，
          通过大小写不敏感精确匹配查找对应记录的 ID，要求名称唯一。
        - 自有 code 字段：某些模型自身包含具有唯一约束的 code 字段
          （如 ``Product.product_code``），这些字段不参与外键解析，
          但可用于唯一性校验（主要在 AddHandler 中使用）以及通过 code 定位记录。
        - 占位自动创建：FK 解析失败时，_AUTO_CREATE_MODELS 中的模型
          会自动创建 abnormal=Placeholder 的占位记录（如价格记录引用了不存在的产品）。

    Attributes:
        _CODE_RESOLVE_MAP: code 字段到 (目标 id 字段, 参照 ORM 模型, 参照表查询列) 的映射。
        _NAME_RESOLVE_MAP: 名称字段到 (对应 code 字段, 目标 id 字段, 参照 ORM 模型, 参照表名称列) 的映射。
        _OWN_CODE_FIELDS: 每个 ORM 模型自身的 code 字段集合，这些字段不会被当作外键处理。
        _NAME_FIELDS: 所有名称中间字段的集合，这些字段仅用于解析，不应持久化到数据库。
        _AUTO_CREATE_MODELS: FK 解析失败时自动创建占位记录的参照模型集合。
    """

    # code 字段 → (对应的 id 字段名, 参照的 ORM 模型, 用于查询的数据库列名)
    _CODE_RESOLVE_MAP: dict[str, tuple[str, type[Base], str]] = {
        "product_code": ("product_id", Product, "product_code"),
    }

    # 名称字段 → (对应的 code 字段, 对应的 id 字段, 参照的 ORM 模型, 用于查询的数据库名称列)
    # 示例实体暂无名称解析；新增实体按需添加，如 {"manager_name": ("manager_code", "manager_id", Manager, "company_name")}
    _NAME_RESOLVE_MAP: dict[str, tuple[str, str, type[Base], str]] = {}

    # 所有名称中间字段的集合（这些字段仅用于查找，不应持久化到数据库）
    _NAME_FIELDS: set = set(_NAME_RESOLVE_MAP.keys())

    # 每个 ORM 模型自身的 code 字段集合（在这里统一定义，可被子类覆盖）
    _OWN_CODE_FIELDS: dict[type[Base], set[str]] = {
        Product: {"product_code"},
    }

    # FK 解析失败时自动创建占位记录的参照模型集合
    _AUTO_CREATE_MODELS: set[type[Base]] = {Product}

    # ORM 自动管理的列，透传和占位构造时需跳过
    _AUTO_MANAGED_COLUMNS: set[str] = {"id", "created_at", "updated_at"}

    _DATE_FIELDS: set = {
        "launch_date",
        "price_date",
    }

    @staticmethod
    def _find_code_col(row: Any) -> str:
        """
        从查询结果行对象中提取一个可读的业务编码，用于构造错误提示。

        优先返回列名以 ``code`` 结尾的字段值，否则回退到记录的主键 ID。

        Args:
            row: 数据库查询返回的 ORM 实例或行对象。

        Returns:
            字符串形式的编码或 ID。
        """
        if isinstance(row, dict):
            for key, value in row.items():
                if key.endswith("_code") and value:
                    return str(value)
            return str(row.get("id") or "N/A")
        for col in row.__table__.columns:
            if col.name.endswith("_code"):
                code_val: Any = getattr(row, col.name, None)
                if code_val is not None:
                    return str(code_val)
        return str(row.id)

    @staticmethod
    def _raise_if_multi_match(
        field_name: str,
        value: str,
        rows: list[dict],
        format_fn: Any,
        hint: str = "请使用 record_id 明确指定",
    ) -> None:
        """若查询到多条记录则抛出 ToolError 并列出候选项。"""
        if len(rows) <= 1:
            return
        candidates = ", ".join(format_fn(r) for r in rows)
        raise ToolError(f"{field_name}='{value}' 匹配到 {len(rows)} 条记录，{hint}: {candidates}")

    @staticmethod
    def _merge_resolved(
        data: dict[str, Any], resolved: dict[str, Any], strip_fields: set
    ) -> dict[str, Any]:
        """
        合并原始数据与解析出的 ID 字段，并移除指定的中间字段。

        合并策略：
            1. 若字段名在 ``strip_fields`` 中，则丢弃该字段（通常是外键 code 字段）。
            2. 若字段名同时出现在 ``data`` 和 ``resolved`` 中，且 ``data`` 中的值不是 ``None``，
               则保留 ``data`` 中的值（显式提供的 ID 优先于解析出的 ID）。
            3. 其他字段直接从 ``data`` 复制。
            4. 最后将 ``resolved`` 中的所有键值对合并到结果中。

        Args:
            data: 原始请求数据字典，可能包含外键 code 字段。
            resolved: 由 code 解析出的 id 字典，例如 ``{"product_id": 42}``。
            strip_fields: 需要移除的字段名集合（通常为外键 code 字段名）。

        Returns:
            合并并清理后的新字典。
        """
        out: dict[str, Any] = {}
        for key, value in data.items():
            # 跳过分组定义为应移除的字段
            if key in strip_fields:
                continue
            # 如果该字段已经通过解析得到且原始值不为 None，则保留原始值（显式 ID 优先）
            if key in resolved and value is not None:
                continue
            out[key] = value
        out.update(resolved)
        return out

    def _fk_code_fields(self, orm_model: type[Base]) -> set[str]:
        """
        获取对于指定 ORM 模型来说需要作为外键处理的 code 字段集合。

        外键 code 字段 = 全部 code 映射字段 - 该模型自身的 code 字段。
        这些字段在解析完成后应当从数据中移除。

        Args:
            orm_model: 目标 ORM 模型类。

        Returns:
            外键 code 字段名的集合。
        """
        own = self._OWN_CODE_FIELDS.get(orm_model, set())
        return set(self._CODE_RESOLVE_MAP.keys()) - own

    @classmethod
    def _ref_passthrough_columns(cls, ref_model: type[Base], lookup_col: str) -> set[str]:
        """
        从 ``ref_model`` 的 ORM 列推导可透传的字段集合。

        排除主键、自动管理列、lookup_col，以及属于其他 code→id 映射目标的列。
        """
        pk_cols = {c.name for c in ref_model.__table__.primary_key.columns}
        id_target_cols = {
            id_field
            for code_field, (id_field, m, _) in cls._CODE_RESOLVE_MAP.items()
            if m is ref_model and code_field != lookup_col
        }
        return {
            c.name
            for c in ref_model.__table__.columns.values()
            if c.name not in pk_cols
            and c.name not in cls._AUTO_MANAGED_COLUMNS
            and c.name != lookup_col
            and c.name not in id_target_cols
        }

    @classmethod
    def _build_placeholder(
        cls,
        ref_model: type[Base],
        lookup_col: str,
        code_val: str,
        extras: dict[str, Any],
    ) -> Base:
        """用内省构建占位记录：无默认值的列用类型感知兜底值填充，extras 覆盖。"""
        kwargs: dict[str, Any] = {lookup_col: code_val}

        for c in ref_model.__table__.columns.values():
            cn = c.name
            if cn in kwargs or cn in extras or cn in cls._AUTO_MANAGED_COLUMNS:
                continue
            if c.server_default is not None or c.primary_key or c.foreign_keys:
                continue
            col_type = getattr(c.type, "impl", c.type)
            if cn == f"{ref_model.__tablename__}_name" and isinstance(col_type, String):
                kwargs[cn] = f"未知{ref_model.__tablename__}-{code_val}"
            elif isinstance(col_type, Date):
                kwargs[cn] = date.today()
            elif isinstance(col_type, (Integer, DECIMAL)):
                kwargs[cn] = 0
            else:
                kwargs[cn] = None

        kwargs["abnormal"] = AbnormalType.Placeholder
        kwargs.update(extras)
        return ref_model(**kwargs)

    async def _resolve_fk_codes(
        self,
        orm_model: type[Base],
        data_list: list[dict[str, Any]],
        db_name: str,
    ) -> list[dict[str, Any]]:
        """
        批量将请求数据中的外键 code 字段解析为对应的数据库 ID，并移除这些 code 字段。

        处理流程：
            1. 遍历全局 code 映射，筛选出属于当前模型外键的字段。
            2. 收集所有需要解析的 code 值（仅当字符串提供且对应 id 未填写）。
            3. 执行一次批量 IN 查询，构建 ``code → id`` 的字典缓存。
            4. 对于每条数据，用缓存中的 id 填充对应的 id 字段；
               若某个 code 在数据库中找不到：_AUTO_CREATE_MODELS 中的模型自动创建占位记录，其余抛出 ValueError。
            5. 通过 ``_merge_resolved`` 合并并移除中间 code 字段。

        Args:
            orm_model: 目标 ORM 模型类，用于区分自有 code 和外键 code。
            data_list: 待处理的原始数据字典列表。
            db_name: 数据库连接名称。

        Returns:
            解析后的数据字典列表，外键 code 字段已被移除，只包含解析后的 id 字段。
        """
        if not data_list:
            return data_list

        own = self._OWN_CODE_FIELDS.get(orm_model, set())
        mgr = await _get_mgr(db_name)
        code_cache: dict[str, dict[str, int]] = {}

        # 第一步：按 code 字段分组收集需要解析的值
        for code_field, (id_field, model, lookup_col) in self._CODE_RESOLVE_MAP.items():
            if code_field in own:
                continue  # 跳过模型自身的 code，不解析
            codes: set[str] = set()
            for d in data_list:
                cv = d.get(code_field)
                # 仅当提供字符串 code 且对应 id 尚未填写时才需要解析
                if isinstance(cv, str) and d.get(id_field) is None:
                    codes.add(cv.strip())
            if not codes:
                continue

            # 第二步：批量查询参照表，构建缓存
            stmt = select(model.id, getattr(model, lookup_col)).where(
                getattr(model, lookup_col).in_(codes)
            )
            rows = await mgr.fetch_all(stmt)
            code_cache[code_field] = {r[lookup_col]: r["id"] for r in rows}

            # 若参照模型支持自动创建且 code 不存在，构建占位记录
            if model in self._AUTO_CREATE_MODELS and codes:
                cache = code_cache[code_field]
                missing = [c for c in codes if c not in cache]
                if missing:
                    passthrough = self._ref_passthrough_columns(model, lookup_col)
                    name_col = f"{model.__tablename__}_name"
                    for mc in missing:
                        # 可能已被前面迭代加入缓存，跳过避免重复插入
                        if mc in cache:
                            continue
                        # 从请求数据中提取该参照模型的透传字段
                        extras: dict[str, Any] = {}
                        candidate_names: list[str] = []
                        for d in data_list:
                            if d.get(code_field, "").strip() == mc:
                                nv = d.get(name_col)
                                if isinstance(nv, str) and nv.strip():
                                    candidate_names.append(nv.strip())
                                for fn in passthrough:
                                    if fn in d and d[fn] is not None and fn not in extras:
                                        if fn != name_col:
                                            extras[fn] = d[fn]
                        # 从候选名称中选最长者作为正式名称
                        if candidate_names:
                            extras[name_col] = max(set(candidate_names), key=len)
                        # 日期字段统一转换
                        for date_fn in self._DATE_FIELDS & passthrough:
                            if date_fn in extras:
                                extras[date_fn] = to_date_flexible(extras[date_fn])

                        placeholder = self._build_placeholder(model, lookup_col, mc, extras)
                        await mgr.insert(placeholder)
                        cache[mc] = placeholder.id

        # 第三步：逐条数据处理
        strip = self._fk_code_fields(orm_model)
        # 非参照自身的模型需移除所有自动创建模型的透传字段
        # 但透传字段若同时是当前模型自身的列（如 data_source），必须保留
        own_cols = {c.name for c in orm_model.__table__.columns.values()}
        for ref_model in self._AUTO_CREATE_MODELS:
            if orm_model is not ref_model:
                for _code_field, (_, m, _lookup) in self._CODE_RESOLVE_MAP.items():
                    if m is ref_model:
                        strip |= self._ref_passthrough_columns(ref_model, _lookup) - own_cols
        resolved_list: list[dict[str, Any]] = []
        for d in data_list:
            resolved: dict[str, Any] = {}
            for code_field, (id_field, model, _) in self._CODE_RESOLVE_MAP.items():
                if code_field in own:
                    continue
                code_val = d.get(code_field)
                if isinstance(code_val, str) and d.get(id_field) is None:
                    cache = code_cache.get(code_field, {})
                    cv = code_val.strip()
                    if cv not in cache:
                        raise ToolError(
                            f"无法解析 {code_field}='{cv}'："
                            f"在 {model.__tablename__} 中未找到匹配记录，请先创建对应的 {model.__tablename__}。",
                            Errcode.RECORD_NOT_FOUND,
                        )
                    resolved[id_field] = cache[cv]
            # 合并解析结果并剔除中间 code 字段
            resolved_list.append(self._merge_resolved(d, resolved, strip))
        return resolved_list

    async def _resolve_names(
        self, data_list: list[dict[str, Any]], db_name: str
    ) -> list[dict[str, Any]]:
        """
        批量将请求数据中的名称字段兜底解析为对应的 ID 字段。

        仅当记录中既未提供外键 code，也未显式提供对应 id 时，才尝试通过名称匹配。
        匹配规则：大小写不敏感精确匹配，且要求名称唯一；若匹配到多条记录或找不到记录则抛出异常。
        解析成功后，所有名称中间字段会从数据中移除，因为这些字段不属于 ORM 属性。

        Args:
            data_list: 经过外键 code 解析后的数据字典列表。
            db_name: 数据库连接名称。

        Returns:
            解析并移除了名称中间字段后的数据字典列表。
        """
        if not data_list:
            return data_list

        mgr = await _get_mgr(db_name)
        for name_field, (code_field, id_field, model, name_col) in self._NAME_RESOLVE_MAP.items():
            # 第一步：收集需要解析的名称
            names: set[str] = set()
            for d in data_list:
                nv = d.get(name_field)
                # 仅当名称存在，且对应的 code 和 id 均未提供时才解析
                if isinstance(nv, str) and not d.get(code_field) and not d.get(id_field):
                    s = nv.strip()
                    if s:
                        names.add(s)
            if not names:
                continue

            # 第二步：大小写不敏感精确匹配查询
            stmt = select(model.id, getattr(model, name_col)).where(
                func.lower(getattr(model, name_col)).in_([n.lower() for n in names])
            )
            rows = await mgr.fetch_all(stmt)
            # 按小写名称分组，以便检测重名
            name_to_rows: dict[str, list[Any]] = {}
            for r in rows:
                key = r[name_col].lower()
                name_to_rows.setdefault(key, []).append(r)

            # 第三步：逐条数据处理
            for d in data_list:
                nv = d.get(name_field)
                if not isinstance(nv, str) or d.get(code_field) or d.get(id_field):
                    continue
                key = nv.strip().lower()
                if not key:
                    continue
                hits = name_to_rows.get(key, [])
                if not hits:
                    raise ToolError(
                        f"无法通过名称 '{nv}' 找到匹配的 {model.__tablename__} 记录，"
                        f"请先创建或提供对应的 code。",
                        Errcode.RECORD_NOT_FOUND,
                    )
                self._raise_if_multi_match(
                    "名称",
                    nv,
                    hits,
                    lambda row, nc=name_col: f"{row[nc]} (code: {self._find_code_col(row)})",
                    hint="请使用 code 明确指定",
                )
                # 将解析出的 id 填入数据
                d[id_field] = hits[0]["id"]

        # 第四步：移除所有名称中间字段，这些字段不是 ORM 属性
        return [{k: v for k, v in d.items() if k not in self._NAME_FIELDS} for d in data_list]

    async def _check_own_codes_unique(
        self,
        orm_model: type[Base],
        data_list: list[dict[str, Any]],
        db_name: str,
        exclude_id: int | None = None,
    ) -> None:
        """
        检查 data_list 中模型自身 code 字段的唯一性，防止重复。

        遍历该模型的自有 code 字段（如 Product 的 ``product_code``），
        首先校验输入数据内部是否有重复值，然后查询数据库是否已存在相同的 code。
        若指定了 ``exclude_id``，则数据库查重时会排除该 ID（用于更新操作的自引用排除）。

        Args:
            orm_model: 目标 ORM 模型类。
            data_list: 待检查的数据字典列表。
            db_name: 数据库连接名称。
            exclude_id: 可选，要排除的记录主键 ID，用于更新时忽略自身。
        """
        own = self._OWN_CODE_FIELDS.get(orm_model, set())
        if not own:
            return
        mgr = await _get_mgr(db_name)

        for code_field, (_, model, lookup_col) in self._CODE_RESOLVE_MAP.items():
            if code_field not in own:
                continue
            # 收集所有非空字符串 code
            codes: list[str] = [
                d[code_field].strip() for d in data_list if isinstance(d.get(code_field), str)
            ]
            if not codes:
                continue

            # 输入内部重复检查
            seen = set()
            dup = None
            for c in codes:
                if c in seen:
                    dup = c
                    break
                seen.add(c)
            if dup is not None:
                raise UniqueConflictError(f"操作失败：{code_field}='{dup}' 在输入数据中重复。")

            # 数据库冲突检查
            stmt = select(model.id, getattr(model, lookup_col)).where(
                getattr(model, lookup_col).in_(codes)
            )
            if exclude_id is not None:
                stmt = stmt.where(model.id != exclude_id)
            rows = await mgr.fetch_all(stmt)
            if rows:
                existing = {r[lookup_col]: r["id"] for r in rows}
                conflicts = [
                    f"{code_field}='{c}' 已存在 (id={existing[c]})" for c in codes if c in existing
                ]
                raise UniqueConflictError(
                    "失败：以下 code 已存在，请使用不同的 code。\n" + "\n".join(conflicts)
                )

    async def _resolve_record_id(
        self,
        orm_model: type[Base],
        record_id: int | None,
        raw: dict[str, object],
        db_name: str,
    ) -> int:
        """
        解析待操作记录的主键 ID。

        优先使用显式提供的 ``record_id``；若未提供，则尝试从 ``raw`` 中获取模型的自有
        code 字段值（例如 ``product_code``），通过查询数据库定位对应的 ID。

        Args:
            orm_model: 目标 ORM 模型类。
            record_id: 直接指定的主键 ID，可为 None。
            raw: 从请求数据中提取的字段字典，可能包含 model 的自有 code。
            db_name: 数据库配置名称。

        Returns:
            解析出的整数主键 ID。
        """
        if record_id is not None:
            mgr = await _get_mgr(db_name)
            stmt = select(orm_model.id).where(orm_model.id == record_id)
            row = await mgr.fetch_one(stmt)
            if row is None:
                raise ToolError(
                    f"{orm_model.__tablename__} 表中未找到 id={record_id} 的记录。",
                    Errcode.RECORD_NOT_FOUND,
                )
            return record_id

        # 尝试通过模型自身的 code 字段解析
        own = self._OWN_CODE_FIELDS.get(orm_model, set())
        mgr = await _get_mgr(db_name)
        for code_field, (_, _model, lookup_col) in self._CODE_RESOLVE_MAP.items():
            if code_field not in own:
                continue
            cv = raw.get(code_field)
            if not isinstance(cv, str):
                continue
            stmt = select(orm_model.id).where(getattr(orm_model, lookup_col) == cv.strip())
            row = await mgr.fetch_one(stmt)
            if row is None:
                raise ToolError(
                    f"{orm_model.__tablename__} 表中未找到 {code_field}='{cv}' 的记录。",
                    Errcode.RECORD_NOT_FOUND,
                )
            return row["id"]

        raise ToolError(
            f"无法识别 {orm_model.__tablename__} 记录：请提供 `record_id` 或唯一的业务编码字段。"
        )

    def _conv_date_fields(self, data_list: list[dict]) -> list[dict]:
        """
        转换日期字段为数据库支持的格式。

        Args:
            data_list: 待处理的数据字典列表。

        Returns:
            处理后的数据字典列表，其中日期字段已转换为数据库支持的格式。
        """
        for row in data_list:
            for field, value in row.items():
                if field in self._DATE_FIELDS and value is not None:
                    row[field] = to_date_flexible(value)
        return data_list
