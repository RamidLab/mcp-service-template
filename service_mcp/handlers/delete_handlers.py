from typing import Any

from sqlalchemy import func, select, update

from service_mcp.error.exceptions import ToolError
from service_mcp.handlers.base_handlers import CodeResolveMixin, _get_mgr
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm import Product, ProductPrice
from service_mcp.models.orm.base import Base
from service_mcp.models.pydantic import BaseDeleteModel
from service_mcp.utils.enums import AbnormalType, Errcode


class DeleteHandler(CodeResolveMixin):
    """
    通用 ORM 模型删除处理器。

    支持通过多种方式定位待删除记录：
        1. record_id — 直接主键
        2. 自有编码字段（product_code）— 唯一业务编码
        3. 额外编码字段 — 按实体注册（_DELETE_EXTRA_CODE）
        4. 复合字段（product_code + price_date 等）— 联合唯一键
        5. 名称字段（product_name 等）— 含同名检测

    名称查找时若匹配到多条记录，会列出所有候选项的编码与 ID，
    供调用方添加编码字段以消除歧义。

    删除父记录时，_ORPHAN_REGISTRY 中注册的子表记录会被标记
    abnormal=Orphaned（软标记），数据保留供人工复核。
    """

    # 额外编码查找：ORM 模型 → [(pydantic 字段名, ORM 列属性)]
    # 示例实体暂无；新增实体按需添加，如管理人的登记编号等
    _DELETE_EXTRA_CODE: dict[type[Base], list] = {}

    # 名称查找：ORM 模型 → [(pydantic 字段名, ORM 名称列属性, ORM 编码列属性)]
    _DELETE_NAME_LOOKUP: dict[type[Base], list] = {
        Product: [("product_name", Product.product_name, Product.product_code)],
    }

    # 复合外键定位注册表：ORM 模型 → (复合字段名列表, WHERE 条件构建器)
    # 复合字段中含 product_code 的会自动解析为 product_id
    _COMPOUND_TARGET_REGISTRY: dict[type[Base], dict[str, Any]] = {
        ProductPrice: {
            "fields": ["product_code", "price_date"],
            "desc": "价格记录",
            "where": lambda fd, d: [
                ProductPrice.product_id == fd.get("product_id"),
                ProductPrice.price_date == d["price_date"],
            ],
            "fk_fields": ["product_code"],
        },
    }

    # 删除前孤儿标记注册表：父模型 → [(子模型, 外键列)]
    _ORPHAN_REGISTRY: dict[type[Base], list[tuple]] = {
        Product: [
            (ProductPrice, ProductPrice.product_id),
        ],
    }

    async def _resolve_compound_target(
        self,
        orm_model: type[Base],
        data_dict: dict[str, Any],
        db_name: str,
    ) -> int | None:
        """为需要通过复合外键定位的模型解析目标 ID。

        使用 _COMPOUND_TARGET_REGISTRY 注册表驱动，避免硬编码 if/elif 链。
        """
        reg = self._COMPOUND_TARGET_REGISTRY.get(orm_model)
        if reg is None:
            return None

        fields = reg["fields"]
        # 检查所有复合字段是否都已提供
        values: dict[str, Any] = {f: data_dict.get(f) for f in fields}
        if not all(
            (isinstance(v, str) and v.strip()) if isinstance(v, str) else v is not None
            for v in values.values()
        ):
            return None

        # 清理字符串字段
        for f in fields:
            v = values[f]
            if isinstance(v, str):
                values[f] = v.strip()

        # 解析 FK code → id
        fk_data = [{f: values[f] for f in reg["fk_fields"]}]
        resolved = await self._resolve_fk_codes(orm_model, fk_data, db_name)

        # 构建 WHERE 条件
        conditions = reg["where"](resolved[0], values)
        stmt = select(orm_model.id).where(*conditions)

        mgr = await _get_mgr(db_name)
        row = await mgr.fetch_one(stmt)
        if row is None:
            field_str = ", ".join(f"{f}={values[f]!r}" for f in fields)
            raise ToolError(f"未找到 {reg['desc']}：{field_str}", Errcode.RECORD_NOT_FOUND)
        return row["id"]

    async def _resolve_delete_target(
        self,
        orm_model: type[Base],
        record_id: int | None,
        data_dict: dict[str, Any],
        db_name: str,
    ) -> int:
        """按优先级依次尝试各种定位方式，返回目标记录的主键 ID。"""
        mgr = await _get_mgr(db_name)

        # ── 1. record_id ──
        if record_id is not None:
            stmt = select(orm_model.id).where(orm_model.id == record_id)
            row = await mgr.fetch_one(stmt)
            if row is None:
                raise ToolError(
                    f"{orm_model.__tablename__} 表中未找到 id={record_id} 的记录。",
                    Errcode.RECORD_NOT_FOUND,
                )
            return record_id

        # ── 2. 自有编码字段（product_code）──
        own = self._OWN_CODE_FIELDS.get(orm_model, set())
        for code_field, (_, _model, lookup_col) in self._CODE_RESOLVE_MAP.items():
            if code_field not in own:
                continue
            cv = data_dict.get(code_field)
            if isinstance(cv, str):
                raw = {code_field: cv.strip()}
                return await self._resolve_record_id(orm_model, None, raw, db_name)

        # ── 3. 额外编码字段 ──
        extra_codes = self._DELETE_EXTRA_CODE.get(orm_model, [])
        for field_name, col_attr in extra_codes:
            extra_val: Any = data_dict.get(field_name)
            if extra_val is None:
                continue
            value = extra_val.strip() if isinstance(extra_val, str) else extra_val
            stmt = select(orm_model.id, col_attr).where(col_attr == value)
            rows = await mgr.fetch_all(stmt)
            if not rows:
                raise ToolError(
                    f"{orm_model.__tablename__} 表中未找到 {field_name}='{value}' 的记录。",
                    Errcode.RECORD_NOT_FOUND,
                )
            self._raise_if_multi_match(
                field_name,
                str(value),
                rows,
                lambda r, fn=field_name, ca=col_attr: f"id={r['id']} ({fn}={r[ca.name]})",
            )
            return rows[0]["id"]

        # ── 4. 复合字段查找 ──
        target_id = await self._resolve_compound_target(orm_model, data_dict, db_name)
        if target_id is not None:
            return target_id

        # ── 5. 名称字段（含同名检测）──
        name_lookups = self._DELETE_NAME_LOOKUP.get(orm_model, [])
        for field_name, col_attr, code_col in name_lookups:
            nv = data_dict.get(field_name)
            if not isinstance(nv, str):
                continue
            name = nv.strip()
            stmt = select(orm_model.id, col_attr, code_col).where(
                func.lower(col_attr) == name.lower()
            )

            rows = await mgr.fetch_all(stmt)
            if not rows:
                raise ToolError(
                    f"{orm_model.__tablename__} 表中未找到 {field_name}='{name}' 的记录。",
                    Errcode.RECORD_NOT_FOUND,
                )
            self._raise_if_multi_match(
                field_name,
                name,
                rows,
                lambda r, ca=col_attr, cc_=code_col: (
                    f"{r[ca.name]} (code: {r[cc_.name] or 'N/A'}, id: {r['id']})"
                ),
                hint="请使用编码或 record_id 明确指定，或提供额外编码以缩小范围",
            )
            return rows[0]["id"]

        raise ToolError(
            f"无法定位 {orm_model.__tablename__} 记录：请提供 record_id、编码字段或名称字段。",
            Errcode.TOOL_MISSING_REQUIRED_PARAM,
        )

    def _build_orphan_statements(
        self,
        orm_model: type[Base],
        target_id: int,
    ) -> list:
        """构建标记孤儿记录的 UPDATE 语句列表。

        使用 _ORPHAN_REGISTRY 注册表驱动：父模型 → [(子模型, 外键列)]。
        返回的语句列表由调用方在共享事务中执行，保证原子性。

        Args:
            orm_model: 父记录的 ORM 模型类。
            target_id: 父记录主键 id。

        Returns:
            待执行的 SQLAlchemy UPDATE 语句列表。
        """
        dependents = self._ORPHAN_REGISTRY.get(orm_model, [])
        if not dependents:
            return []
        return [
            update(child_model).where(fk_col == target_id).values(abnormal=AbnormalType.Orphaned)
            for child_model, fk_col in dependents
        ]

    async def handle(
        self,
        orm_model: type[Base],
        data: BaseDeleteModel,
        db_name: str = "default",
    ) -> UtilResponse[dict[str, int]]:
        """
        删除单条 ORM 记录。

        定位优先级：
            1. record_id
            2. 自有编码字段（如 product_code）
            3. 额外编码字段
            4. 复合字段（如 product_code + price_date）
            5. 名称字段（如 product_name），同名时报错并列出候选项

        Args:
            orm_model: 目标 ORM 模型类。
            data: Pydantic 删除模型，包含定位字段。
            db_name: 数据库配置名称，默认为 "default"。

        Returns:
            UtilResponse，包含已删除记录的 id。
        """
        data_dict = data.model_dump(exclude_none=True)
        record_id = data_dict.pop("record_id", None)

        target_id = await self._resolve_delete_target(orm_model, record_id, data_dict, db_name)

        # 在同一事务内标记孤儿 + 删除父记录
        orphan_stmts = self._build_orphan_statements(orm_model, target_id)
        mgr = await _get_mgr(db_name)
        await mgr.delete_with_orphans(orm_model, target_id, orphan_stmts)
        return UtilResponse(code=Errcode.SUCCESS, message="删除成功。", data={"id": target_id})

    async def handle_batch(
        self, orm_model: type[Base], data_list: list[BaseDeleteModel], db_name: str = "default"
    ) -> UtilResponse[dict[str, Any]]:
        """
        批量删除 ORM 记录。

        每条数据使用与单条删除相同的定位逻辑（record_id / 编码 / 复合字段 / 名称），
        解析出目标 ID 后统一批量删除。重名检测等校验与单条删除行为一致。

        Args:
            orm_model: 目标 ORM 模型类。
            data_list: Pydantic 删除模型列表，每项包含定位字段。
            db_name: 数据库配置名称，默认为 "default"。

        Returns:
            UtilResponse，data 中包含已删除的 id 列表与总数量。
            若 data_list 为空，直接返回成功但 count 为 0。
        """
        if not data_list:
            return UtilResponse(
                code=Errcode.SUCCESS, message="没有需要删除的记录。", data={"count": 0}
            )

        target_ids: list[int] = []
        for data in data_list:
            data_dict = data.model_dump(exclude_none=True)
            record_id = data_dict.pop("record_id", None)
            target_id = await self._resolve_delete_target(orm_model, record_id, data_dict, db_name)
            target_ids.append(target_id)

        unique_ids = list(dict.fromkeys(target_ids))

        # 在同一事务内标记所有孤儿 + 批量删除父记录
        all_orphan_stmts = []
        for tid in unique_ids:
            all_orphan_stmts.extend(self._build_orphan_statements(orm_model, tid))

        mgr = await _get_mgr(db_name)
        count = await mgr.delete_batch_with_orphans(orm_model, unique_ids, all_orphan_stmts)
        return UtilResponse(
            code=Errcode.SUCCESS,
            message="批量删除成功。",
            data={"ids": unique_ids, "count": count},
        )
