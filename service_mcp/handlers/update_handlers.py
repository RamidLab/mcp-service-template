from datetime import datetime
from typing import Any

from pydantic import BaseModel

from service_mcp.error.exceptions import ToolError
from service_mcp.handlers.base_handlers import CodeResolveMixin, _get_mgr
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm.base import Base
from service_mcp.utils.enums import Errcode


class UpdateHandler(CodeResolveMixin):
    """
    通用的 ORM 模型更新处理器。

    通过 `record_id`（主键）或模型的唯一业务编码字段定位记录，
    然后仅将更新 Pydantic 模型中非 None 的字段应用到数据库。
    外键编码 → id 以及名称 → id 的解析能力继承自 CodeResolveMixin。
    """

    async def handle(
        self,
        orm_model: type[Base],
        data: BaseModel,
        record_id: int | None,
        db_name: str = "default",
    ) -> UtilResponse[dict[str, Any]]:
        """
        更新单条 ORM 记录。

        Args:
            orm_model: 目标 ORM 模型类。
            data: 包含待应用字段的 Pydantic 更新模型。
            record_id: 主键定位；若未提供，则回退到模型的唯一编码字段（例如 product_code）进行定位。
            db_name: 数据库配置名称。

        Returns:
            UtilResponse，data 包含 id 和 _extra（非 ORM 列字段，供 tool 层后处理）。
        """
        raw = data.model_dump()

        # 若未提供 record_id，则从数据中提取自有编码字段用于定位
        own = self._OWN_CODE_FIELDS.get(orm_model, set())
        identifying_codes: dict[str, str] = {}
        if record_id is None:
            for cf in own:
                if isinstance(raw.get(cf), str):
                    identifying_codes[cf] = raw.pop(cf)

        # 解析主键 id
        lookup = {**raw, **identifying_codes}
        target_id = await self._resolve_record_id(orm_model, record_id, lookup, db_name)

        # 剔除值为 None 的字段 —— 只应用明确给出的值
        update_fields = {k: v for k, v in raw.items() if v is not None}
        if not update_fields:
            return UtilResponse(
                code=Errcode.SUCCESS, message="没有需要更新的字段。", data={"id": target_id}
            )

        # 外键与名称解析
        resolved_list = await self._resolve_fk_codes(orm_model, [update_fields], db_name)
        resolved_list = await self._resolve_names(resolved_list, db_name)
        final = resolved_list[0]

        # 校验自有编码不与数据库中其他记录冲突
        await self._check_own_codes_unique(orm_model, [final], db_name, exclude_id=target_id)

        final["updated_at"] = datetime.now()

        mgr = await _get_mgr(db_name)
        instance = await mgr.update_by_id(orm_model, target_id, final)
        return UtilResponse(code=Errcode.SUCCESS, message="更新成功。", data={"id": instance.id})

    async def handle_batch(
        self,
        orm_model: type[Base],
        ids: list[int],
        data_list: list[BaseModel],
        db_name: str = "default",
    ) -> UtilResponse[dict[str, int]]:
        """
        批量更新 ORM 记录。

        Args:
            orm_model: 目标 ORM 模型类。
            ids: 要更新的记录主键 id 列表。
            data_list: 与 ids 顺序对应的 Pydantic 更新模型列表。
            db_name: 数据库配置名称。

        Returns:
            UtilResponse，包含更新成功的 id 列表及数量。
        """
        if not data_list:
            return UtilResponse(
                code=Errcode.SUCCESS, message="没有需要更新的记录。", data={"count": 0}
            )
        if len(ids) != len(data_list):
            raise ToolError(f"数量不匹配：{len(ids)} 个 ID 与 {len(data_list)} 条数据不一致。")

        raws = [d.model_dump() for d in data_list]
        cleaned: list[dict[str, Any]] = [
            {k: v for k, v in r.items() if v is not None} for r in raws
        ]

        # 外键与名称解析
        resolved = await self._resolve_fk_codes(orm_model, cleaned, db_name)
        resolved = await self._resolve_names(resolved, db_name)

        # 校验自有编码不与数据库中其他记录冲突
        for rid, fields in zip(ids, resolved):
            await self._check_own_codes_unique(orm_model, [fields], db_name, exclude_id=rid)

        now = datetime.now()
        for fields in resolved:
            fields["updated_at"] = now

        mgr = await _get_mgr(db_name)
        updated_ids = await mgr.update_batch_by_ids(orm_model, ids, resolved)

        return UtilResponse(
            code=Errcode.SUCCESS,
            message="批量更新成功。",
            data={"ids": updated_ids, "count": len(updated_ids)},
        )
