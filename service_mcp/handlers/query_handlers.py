from string import Formatter
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from service_mcp.db.core import DBManager
from service_mcp.handlers.base_handlers import _get_mgr, owner_visibility_where
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm import Base, Product, ProductPrice
from service_mcp.models.pydantic import BaseFilter, BaseSearchByFields, BaseSearchByKeyword
from service_mcp.models.schemas import PageData, PaginationParams
from service_mcp.utils.enums import AbnormalType, Errcode


class QueryHandler:
    """
    通用查询处理类

    负责分页查询、过滤、排序，并可选地将结果中的外键 ID 替换为关联对象的可读字段，
    使 API 响应直接呈现业务信息，避免暴露内部 ID。

    核心功能：
        1. 支持 BaseFilter / BaseSearchByKeyword / BaseSearchByFields 构建查询条件。
        2. 通过 PaginationParams 实现分页与排序。
        3. 根据字段映射配置，将外键 ID 转换为关联对象上的指定字段，
           支持嵌套关系预加载（select in load），避免 N+1 查询。

    配置方式：
        默认使用类属性 FIELD_MAPPING_CONFIG。实例化时也可通过参数 field_mapping
        动态覆盖，实现不同业务场景的复用。

    Usage:
        # 使用默认映射
        handler = QueryHandler()
        resp = await handler.handle(ProductPrice, params, filter_, db_name)

        # 使用自定义映射
        custom_mapping = {...}
        handler = QueryHandler(field_mapping=custom_mapping)
    """

    # 模型级外键映射配置：
    # 结构：{ 主模型: { 外键字段名: (关联模型, [显示字段映射列表]) } }
    # 显示字段映射元素可为 str（同名字段）或 (源属性路径, 输出字段名) 元组
    FIELD_MAPPING_CONFIG: dict[
        type[Base], dict[str, tuple[type[Base], list[str | tuple[str, str]]]]
    ] = {
        ProductPrice: {
            "product_id": (Product, ["product_name", "product_code"]),
        },
    }

    def __init__(
        self,
        field_mapping: dict[type[Base], dict[str, tuple[type[Base], list[str | tuple[str, str]]]]]
        | None = None,
    ):
        """
        初始化查询处理器。

        Args:
            field_mapping: 可选的外键映射配置，格式与 FIELD_MAPPING_CONFIG 相同。
                           若为 None，则使用类默认配置。
        """
        self.field_mapping = field_mapping or self.__class__.FIELD_MAPPING_CONFIG

    @staticmethod
    def _parse_field_mapping(mapping: str | tuple[str, str]) -> tuple[str, str]:
        """
        解析单个字段映射，统一为 (源属性路径, 输出字段名) 的元组。

        Args:
            mapping: 字段映射，可以是字符串（同名字段）或 (源属性, 输出字段) 元组。

        Returns:
            (source_attr, output_field) 元组，分别表示源属性路径和输出字段名。
        """
        if isinstance(mapping, str):
            return mapping, mapping
        if isinstance(mapping, tuple) and len(mapping) == 2:
            return mapping
        raise ValueError(f"无效的字段映射: {mapping}")

    @classmethod
    def _prepare_field_mappings(
        cls, model: type[Base], config: dict
    ) -> dict[str, tuple[type[Base], list[tuple[str, str]], list[str]]]:
        """
        解析指定模型的字段映射配置。

        Args:
            model: ORM 模型类。
            config: 外键映射配置字典（完整，非仅当前模型）。

        Returns:
            该模型的解析后映射，便于后续批量查询和字段替换。
        """
        raw = config.get(model, {})
        result: dict[str, tuple[type[Base], list[tuple[str, str]], list[str]]] = {}
        for fk_field, (related_model, raw_mappings) in raw.items():
            parsed = [cls._parse_field_mapping(m) for m in raw_mappings]
            nested = list({src.split(".")[0] for src, _ in parsed if "." in src})
            result[fk_field] = (related_model, parsed, nested)
        return result

    @staticmethod
    async def _fetch_related(
        items: list[dict[str, Any]],
        mapping: dict[str, tuple[type[Base], list[tuple[str, str]], list[str]]],
        db_name: str,
    ) -> dict[str, dict[int, Base]]:
        """
        批量查询外键关联对象，返回 ID -> ORM 对象的缓存。

        Args:
            items: 结果字典列表。
            mapping: 当前模型的外键映射（已解析）。
            db_name: 数据库名称。

        Returns:
            外键字段名到 {ID: ORM对象} 的二级缓存。
        """
        if not mapping:
            return {}

        mgr: DBManager = await _get_mgr(db_name)
        cache: dict[str, dict[int, Base]] = {}

        for fk_field, (related_model, _, nested_rels) in mapping.items():
            ids = {item[fk_field] for item in items if item.get(fk_field) is not None}
            if not ids:
                continue

            stmt = select(related_model)
            if nested_rels:
                options = [
                    selectinload(getattr(related_model, rel))
                    for rel in nested_rels
                    if hasattr(related_model, rel)
                ]
                stmt = stmt.options(*options)
            stmt = stmt.where(related_model.id.in_(ids))

            async with mgr.get_session() as session:
                rows = (await session.execute(stmt)).scalars().all()

            cache[fk_field] = {obj.id: obj for obj in rows}
        return cache

    @classmethod
    def _apply_mapping(
        cls,
        items: list[dict[str, Any]],
        mapping: dict[str, tuple[type[Base], list[tuple[str, str]], list[str]]],
        cache: dict[str, dict[int, Base]],
    ) -> list[dict[str, Any]]:
        """
        将 items 中的外键 ID 替换为关联对象的可读字段。

        Args:
            items: 原始结果列表。
            mapping: 已解析的外键映射。
            cache: 关联对象缓存。

        Returns:
            替换后的字典列表，外键列被移除。
        """
        if not mapping:
            return items

        converted = []
        for item in items:
            new_item = {}
            for key, value in item.items():
                if key in mapping:
                    ref_id = value
                    if ref_id is not None and key in cache:
                        obj = cache[key].get(ref_id)
                        if obj:
                            _, parsed_mappings, _ = mapping[key]
                            for src_path, out_field in parsed_mappings:
                                try:
                                    val = obj
                                    for attr in src_path.split("."):
                                        val = getattr(val, attr)
                                    new_item[out_field] = val
                                except AttributeError:
                                    new_item[out_field] = None
                    # 不保留原始外键列
                    continue
                new_item[key] = value
            converted.append(new_item)
        return converted

    async def handle(
        self,
        model: type[Base],
        params: PaginationParams,
        filter_or_search: BaseFilter | BaseSearchByKeyword | BaseSearchByFields | None,
        db_name: str,
        extra_where: list | None = None,
    ) -> UtilResponse[PageData]:
        """
        执行分页查询并应用外键字段展开，返回统一响应。

        Args:
            model: 目标 ORM 模型类。
            params: 分页参数。
            filter_or_search: 过滤或搜索条件。
            db_name: 数据库配置名称。
            extra_where: 额外的 SQLAlchemy WHERE 条件列表。

        Returns:
            UtilResponse，data 为 PageData，其中 items 已展开外键字段。
        """
        mgr = await _get_mgr(db_name)

        # 构建查询条件
        where = order_by = None
        if filter_or_search is not None:
            if isinstance(filter_or_search, BaseFilter):
                where = filter_or_search.to_where()
                order_by = filter_or_search.to_order_by()
            elif isinstance(filter_or_search, (BaseSearchByKeyword, BaseSearchByFields)):
                where = filter_or_search.to_where()
            else:
                raise TypeError(f"不支持的过滤器类型: {type(filter_or_search)}")

        # 叠加数据范围过滤（令牌级 PermScope：ALL/OWN/CUSTOM）
        scope_where = self._build_data_scope_where(model)
        if scope_where is not None:
            where = where + scope_where if where is not None else scope_where

        # 归属隔离：模型带 data_scope 走三级可见性；带 owner 列走旧两态；均无则不过滤
        owner_where = owner_visibility_where(model)
        if owner_where:
            where = where + owner_where if where is not None else owner_where

        # 父实体可见性：无自身归属列的注册子表按"所属父实体可见"过滤（孤儿行豁免）
        parent_where = self._parent_visibility_where(model)
        if parent_where:
            where = where + parent_where if where is not None else parent_where

        # 叠加额外条件
        if extra_where:
            where = where + extra_where if where is not None else extra_where

        # 软删行默认隐藏：模型带 is_deleted 列时列表/搜索不返回已软删记录
        # （软删即视为已删，墓碑行仅供后台清理，不应出现在任何对外查询中）
        if hasattr(model, "is_deleted"):
            deleted_cond = model.is_deleted.is_(False)
            where = [*where, deleted_cond] if where is not None else [deleted_cond]

        # 分页查询
        page_data: PageData[dict[str, Any]] = await mgr.paginate(
            model, params, where=where, order_by=order_by
        )

        # 准备字段映射（使用实例的 field_mapping 配置）
        prepared = self._prepare_field_mappings(model, self.field_mapping)

        # 批量获取关联对象并应用映射
        cache = await self._fetch_related(page_data.items, prepared, db_name)
        mapped_items = self._apply_mapping(page_data.items, prepared, cache)

        final_page = PageData.create(mapped_items, params, page_data.pagination.total)
        return UtilResponse(code=Errcode.SUCCESS, message="查询成功", data=final_page)

    @staticmethod
    def _scope_visibility_where(model: type[Base]) -> list:
        """模型级三级可见性条件（唯一来源：auth.context.scope_visibility_where）。

        读取带归属列（data_scope/owner_id/publish_status）的表时一律经此取条件，
        保证列表/富化/聚合与明细查询口径同源：
          - 无鉴权上下文（tool 模式、后台任务）：返回空列表，即不过滤；
          - 模型无 data_scope 列：返回空列表（调用方可再叠加旧口径）；
          - 其余按 platform/team/personal 与 PENDING/REJECTED 规则过滤。
        """
        from service_mcp.auth.context import scope_visibility_where  # 延迟导入避免循环引用

        return scope_visibility_where(model) or []

    @classmethod
    def _parent_visibility_where(cls, model: type[Base]) -> list:
        """父实体可见性条件：无自身归属列的子表按"所属父实体可见"过滤。

        声明见 service_mcp.models.orm 的 PARENT_ENTITY_MAP（handler 内不写实体分支，
        新增同类子表只需在注册表登记一行）；条件来源仍是同一个可见性引擎，
        只是作用在父实体上，与父实体列表口径完全一致。

        孤儿口径：父外键为空、或父实体行已不存在时不施加父可见性约束 ——
        孤儿行没有可保护的"父归属"，且孤儿必须保持可见才能被维护/复核。
        """
        if hasattr(model, "data_scope") or hasattr(model, "owner"):
            return []  # 自身带归属列：按自身规则，不再叠加父规则
        from service_mcp.models.orm import PARENT_ENTITY_MAP

        entry = PARENT_ENTITY_MAP.get(model)
        if entry is None:
            return []
        parent, fk_name = entry
        parent_vis = cls._scope_visibility_where(parent)
        if not parent_vis:
            # 父实体无 data_scope 列时回落旧两态 owner 口径
            parent_vis = owner_visibility_where(parent) or []
        if not parent_vis:
            return []

        fk_col = getattr(model, fk_name)
        parent_exists = select(1).where(parent.id == fk_col).correlate(model).exists()
        parent_visible = (
            select(1).where(parent.id == fk_col, *parent_vis).correlate(model).exists()
        )
        return [or_(~parent_exists, parent_visible)]

    @staticmethod
    def _build_data_scope_where(model: type[Base]):
        """从当前权限上下文提取数据范围，构建 SQLAlchemy WHERE 条件。

        支持的数据范围类型：
            - ALL：不添加任何过滤
            - OWN：created_by = 当前用户（如果模型有 created_by 列）
            - CUSTOM：按自定义 scope 过滤（示例实现仅支持 OWN 语义，
              新项目可按业务扩展 TAG/PROJECT 等范围类型）
        """
        from service_mcp.auth.context import get_current_scope  # 延迟导入避免循环引用

        scope = get_current_scope()
        if scope is None or scope.data_scope == "ALL":
            return None

        conditions = []
        if scope.data_scope == "OWN":
            if hasattr(model, "created_by"):
                from service_mcp.auth.context import get_auth_context

                ctx = get_auth_context()
                if ctx:
                    conditions.append(model.created_by == ctx.user_id)

        if conditions:
            return conditions
        return None

    @staticmethod
    def _make_product_label(row: dict[str, Any]) -> str:
        name = row.get("product_name") or "?"
        code = row.get("product_code") or "?"
        return f"「{name}」(code={code})"

    @staticmethod
    def _build_abnormal_item(
        source_table: str,
        row: dict[str, Any],
        summary: str,
        severity: str,
        context: dict[str, Any],
        enum_type: type,
        enum_value: int,
    ) -> dict[str, Any]:
        """构建标准化的异常待办项字典。"""
        try:
            member = enum_type(enum_value)
        except ValueError:
            member = None
        label = getattr(member, "label", f"未知({enum_value})")
        return {
            "source_table": source_table,
            "source_id": row["id"],
            "abnormal_type": enum_value,
            "abnormal_label": label,
            "summary": summary,
            "severity": severity,
            "created_at": str(row["created_at"]) if row.get("created_at") else None,
            "context": context,
        }

    async def _collect_product_abnormal(
        self, mgr: DBManager, severity_filter: str | None
    ) -> list[dict[str, Any]]:
        stmt = select(
            Product.id,
            Product.product_code,
            Product.product_name,
            Product.abnormal,
            Product.created_at,
        ).where(Product.abnormal.isnot(None))
        rows = await mgr.fetch_all(stmt)
        items = []
        for r in rows:
            at = AbnormalType(r["abnormal"])
            if severity_filter and at.severity != severity_filter:
                continue
            items.append(
                self._build_abnormal_item(
                    source_table="product",
                    row=r,
                    summary=f"产品「{r['product_name']}」(code={r['product_code']})：{at.label}",
                    severity=at.severity,
                    enum_type=AbnormalType,
                    enum_value=int(at),
                    context={"product_code": r["product_code"], "product_name": r["product_name"]},
                )
            )
        return items

    async def _collect_child_abnormal(
        self,
        mgr: DBManager,
        severity_filter: str | None,
        model: type[Base],
        source_table: str,
        summary_tpl: str,
        context_keys: list[str],
    ) -> list[dict[str, Any]]:
        """通用的子表异常记录收集器（ProductPrice 等）。

        Args:
            mgr: 数据库管理器
            severity_filter: 严重程度过滤
            model: 子表 ORM 模型（如 ProductPrice）
            source_table: 来源表名标识（如 "product_price"）
            summary_tpl: 摘要模板，支持 {product_label}、{at_label} 及 row 中的字段名
            context_keys: 从 row 中提取到 context 的字段名列表
        """
        product_cols = [Product.product_code, Product.product_name]
        t = model.__table__
        product_id_col = t.c.product_id
        abnormal_col = t.c.abnormal
        child_cols = [t.c.id, product_id_col, abnormal_col, t.c.created_at]
        # 自动收集模型中与 context_keys 对应的列
        for key in context_keys:
            col = t.c.get(key)
            if col is not None and col not in child_cols:
                child_cols.append(col)

        stmt = (
            select(*child_cols, *product_cols)
            .join(
                Product,
                product_id_col == Product.id,
                isouter=True,
            )
            .where(abnormal_col.isnot(None))
        )
        rows = await mgr.fetch_all(stmt)

        tpl_keys = {
            field_name for _, field_name, _, _ in Formatter().parse(summary_tpl) if field_name
        }
        tpl_keys -= {"product_label", "at_label"}

        items = []
        for r in rows:
            at = AbnormalType(r["abnormal"])
            if severity_filter and at.severity != severity_filter:
                continue
            product_label = self._make_product_label(r)
            context = {k: str(r[k]) if r.get(k) is not None else None for k in context_keys}
            context["product_id"] = r.get("product_id")
            fmt_args = {k: r[k] for k in tpl_keys if k in r}
            items.append(
                self._build_abnormal_item(
                    source_table=source_table,
                    row=r,
                    summary=summary_tpl.format(
                        product_label=product_label, at_label=at.label, **fmt_args
                    ),
                    severity=at.severity,
                    enum_type=AbnormalType,
                    enum_value=int(at),
                    context=context,
                )
            )
        return items

    async def review_abnormal_items(
        self,
        params: PaginationParams,
        severity: str | None = None,
        source_table: str | None = None,
        db_name: str = "default",
    ) -> UtilResponse[PageData]:
        mgr = await _get_mgr(db_name)

        # 收集器配置：(表标识, 收集函数)
        collectors: list[tuple[str, Any]] = [
            ("product", lambda m, s: self._collect_product_abnormal(m, s)),
            (
                "product_price",
                lambda m, s: self._collect_child_abnormal(
                    m,
                    s,
                    ProductPrice,
                    "product_price",
                    summary_tpl="产品{product_label} 价格{at_label}（日期={price_date}, 版本=v{version}）",
                    context_keys=["price_date", "version"],
                ),
            ),
        ]

        if source_table:
            collectors = [(st, fn) for st, fn in collectors if st == source_table]
            if not collectors:
                valid = "product, product_price"
                return UtilResponse(
                    code=Errcode.FAIL,
                    message=f"无效的 source_table: {source_table}，可选值: {valid}",
                    data=PageData.create([], params, 0),
                )

        all_items: list[dict[str, Any]] = []
        for _st, collector_fn in collectors:
            batch = await collector_fn(mgr, severity)
            all_items.extend(batch)

        all_items.sort(key=lambda it: str(it.get("created_at") or ""), reverse=True)

        total = len(all_items)
        paged = all_items[params.offset : params.offset + params.page_size]

        return UtilResponse(
            code=Errcode.SUCCESS,
            message=f"共 {total} 条待办项",
            data=PageData.create(paged, params, total),
        )
