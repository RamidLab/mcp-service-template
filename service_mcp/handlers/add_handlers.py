import re
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from service_mcp.error.exceptions import UniqueConflictError
from service_mcp.handlers.base_handlers import CodeResolveMixin, _get_mgr
from service_mcp.models.common import UtilResponse
from service_mcp.models.orm import ProductPrice
from service_mcp.models.orm.base import Base
from service_mcp.utils.enums import AbnormalType, Errcode
from service_mcp.utils.log import get_logger


logger = get_logger(__name__)


class AddHandler(CodeResolveMixin):
    """
    通用数据添加处理类

    负责将 Pydantic 创建模型转换为 ORM 实例并持久化到数据库。
    支持单条及批量添加，并直接复用 CodeResolveMixin 提供的外键 code → id 解析和名称 → id 兜底解析。

    核心机制：
        1. 识别请求数据中的业务 code 字段（如 product_code、manager_code 等），
           通过基类方法将它们转换为对应的外键 ID。
        2. 对于某些模型自身的 code 字段（如 Product 的 product_code），会进行唯一性校验，
           确保不会重复或与已有数据冲突。
        3. 如果没有提供 code，但提供了可读的名称字段，则通过基类方法进行名称匹配并回填对应的 ID。

    Note:
        本类中的“code”泛指业务上的唯一标识字符串，不限于数据库主键，例如产品代码、机构编号等。
    """

    @classmethod
    def _get_column_labels(cls, orm_model: type[Base]) -> dict[str, str]:
        """从 ORM 模型列的 comment 中提取 列名→中文标签 映射."""
        labels: dict[str, str] = {}
        for col in orm_model.__table__.columns.values():
            comment = (col.comment or "").strip()
            if not comment:
                continue
            # comment 可能附带补充说明，取第一个逗号/顿号前的部分作为短标签
            label = re.split(r"[，,]", comment)[0]
            labels[col.name] = label
        return labels

    @classmethod
    def _parse_constraint_columns(cls, e: IntegrityError) -> tuple[str | None, list[str]]:
        """从 IntegrityError 中提取表名和冲突列名列表."""
        orig = str(getattr(e, "orig", e))
        match = re.search(r"UNIQUE constraint failed:\s*(\S.*)", orig)
        if not match:
            return None, []
        cols_part = match.group(1)
        table: str | None = None
        cols: list[str] = []
        for seg in cols_part.split(","):
            seg = seg.strip()
            if "." in seg:
                t, c = seg.split(".", 1)
                if table is None:
                    table = t
                cols.append(c)
            else:
                cols.append(seg)
        return table, cols

    @classmethod
    def _format_integrity_error(
        cls,
        e: IntegrityError,
        raw: dict | None = None,
        orm_model: type[Base] | None = None,
    ) -> str:
        """将 IntegrityError 转换为用户可读的中文消息."""
        _table, cols = cls._parse_constraint_columns(e)
        if not cols:
            return f"数据重复：{getattr(e, 'orig', e)}"
        labels = cls._get_column_labels(orm_model) if orm_model else {}
        parts: list[str] = []
        for c in cols:
            label = labels.get(c, c)
            if raw and c in raw and raw[c] is not None:
                parts.append(f"「{label}={raw[c]}」")
            else:
                parts.append(f"「{label}」")
        return f"数据重复：{', '.join(parts)} 的组合已存在，请勿重复添加"

    @classmethod
    def _extract_conflict_key(cls, e: IntegrityError, raw: dict) -> dict[str, str]:
        """从 IntegrityError 中提取冲突列名，从 raw 中取出对应值组成 key."""
        _table, cols = cls._parse_constraint_columns(e)
        key: dict[str, str] = {}
        for c in cols:
            if c in raw and raw[c] is not None:
                key[c] = str(raw[c])
        if not key:
            key = {
                k: (v if isinstance(v, str) else str(v)) if v is not None else ""
                for k, v in raw.items()
                if k.endswith(("_code", "_date")) and v is not None
            }
        return key

    @staticmethod
    async def _detect_price_conflict(raw: dict[str, Any], db_name: str) -> dict[str, Any]:
        """检测价格冲突：同日同源但值不同，自动升版本并标注需人工审核。

        仅当新记录与已有记录在共同非空字段上存在数值差异时，才视为冲突。
        若新记录只是已有记录的子集（如同一产品同一日，新记录仅有单位价格但
        缺少累计价格，而已有记录两者皆有且单位价格一致），不触发版本升级。
        """
        mgr = await _get_mgr(db_name)
        product_id = raw.get("product_id")
        price_date = raw.get("price_date")
        data_source = raw.get("data_source")
        if product_id is None or price_date is None or data_source is None:
            return raw

        existing = await mgr.fetch_all(
            select(
                ProductPrice.unit_price,
                ProductPrice.acc_price,
                ProductPrice.daily_return_rate,
                ProductPrice.version,
            ).where(
                ProductPrice.product_id == product_id,
                ProductPrice.price_date == price_date,
                ProductPrice.data_source == data_source,
            )
        )
        if not existing:
            return raw

        price_fields = ("unit_price", "acc_price", "daily_return_rate")
        new_vals = {f: raw.get(f) for f in price_fields}

        for r in existing:
            # 完全一致 → 无冲突，交由 IntegrityError 处理
            if all(r[f] == new_vals[f] for f in price_fields):
                return raw

            # 重叠字段比较：双方都有值的字段全匹配 → 兼容，不视为冲突
            compatible = True
            for f in price_fields:
                ev = r[f]
                nv = new_vals[f]
                if ev is not None and nv is not None and ev != nv:
                    compatible = False
                    break
            if compatible:
                return raw

        max_ver = max(r["version"] for r in existing)
        raw["version"] = max_ver + 1
        raw["abnormal"] = AbnormalType.PriceConflict
        return raw

    async def _prepare_records(
        self,
        orm_model: type[Base],
        data_list: list[BaseModel],
        db_name: str,
    ) -> list[dict[str, Any]]:
        """批量预处理：唯一性校验 → 解析外键 → 名称兜底 → 日期转换。

        Args:
            orm_model: 目标 ORM 模型类。
            data_list: Pydantic 创建模型列表。
            db_name: 数据库名称。

        Returns:
            处理后的原始字典列表。

        Raises:
            ValueError: 唯一性冲突（来自 _check_own_codes_unique）
            ValueError: 外键/名称解析失败（来自 _resolve_fk_codes / _resolve_names）
        """
        raws = [d.model_dump() for d in data_list]
        # 阶段 1：唯一性校验（独立错误码）
        await self._check_own_codes_unique(orm_model, raws, db_name)
        # 阶段 2：FK 解析 + 名称兜底 + 日期转换
        raws = await self._resolve_fk_codes(orm_model, raws, db_name)
        raws = await self._resolve_names(raws, db_name)
        raws = self._conv_date_fields(raws)
        return raws

    async def _insert_single(
        self,
        orm_model: type[Base],
        raw: dict[str, Any],
        db_name: str,
    ) -> UtilResponse[dict[str, Any]]:
        """插入单条记录（含价格冲突检测和 IntegrityError 处理）。"""
        if orm_model is ProductPrice:
            raw = await self._detect_price_conflict(raw, db_name)

        mgr = await _get_mgr(db_name)
        try:
            instance = orm_model(**raw)
            await mgr.insert(instance)
            return UtilResponse(code=Errcode.SUCCESS, message="添加成功", data={"id": instance.id})
        except IntegrityError as e:
            return UtilResponse(
                code=Errcode.UNIQUE_CONFLICT,
                message=self._format_integrity_error(e, raw, orm_model),
                data={"id": None, "conflict_key": self._extract_conflict_key(e, raw)},
            )
        except (TypeError, AttributeError, OperationalError) as e:
            logger.exception("插入 %s 失败", orm_model.__tablename__)
            return UtilResponse(
                code=Errcode.FAIL,
                message=f"添加失败: {e}",
                data={"id": None},
            )

    async def handle(
        self,
        orm_model: type[Base],
        data: BaseModel,
        db_name: str = "default",
    ) -> UtilResponse[dict[str, Any]]:
        """
        添加单条 ORM 记录。

        Args:
            orm_model: 目标 ORM 模型类。
            data: 包含待添加字段的 Pydantic 创建模型。
            db_name: 数据库配置名称，默认为 "default"。

        Returns:
            UtilResponse，包含新记录的 id。
        """
        try:
            raws = await self._prepare_records(orm_model, [data], db_name)
        except UniqueConflictError as e:
            return UtilResponse(code=Errcode.UNIQUE_CONFLICT, message=str(e), data={"id": None})
        except Exception as e:
            return UtilResponse(code=Errcode.FAIL, message=str(e), data={"id": None})
        return await self._insert_single(orm_model, raws[0], db_name)

    async def handle_batch(
        self, orm_model: type[Base], data_list: list[BaseModel], db_name: str = "default"
    ) -> UtilResponse[dict[str, Any]]:
        """
        批量添加记录，支持部分失败——单条异常不影响其他记录。

        Args:
            orm_model: 目标 ORM 模型类。
            data_list: Pydantic 创建模型实例列表。
            db_name: 数据库连接名称，默认为 "default"。

        Returns:
            UtilResponse，data 中包含成功数量、失败数量、成功 ID 列表和失败详情。
        """
        total = len(data_list)

        try:
            raws = await self._prepare_records(orm_model, data_list, db_name)
        except Exception as e:
            code = Errcode.UNIQUE_CONFLICT if isinstance(e, UniqueConflictError) else Errcode.FAIL
            return UtilResponse(
                code=code,
                message=str(e),
                data={
                    "success_count": 0,
                    "fail_count": total,
                    "ids": [],
                    "failures": [{"index": 0, "key": {}, "error": str(e)}],
                },
            )

        mgr = await _get_mgr(db_name)
        success_ids: list[int] = []
        failures: list[dict] = []

        for i, raw in enumerate(raws):
            try:
                if orm_model is ProductPrice:
                    raw = await self._detect_price_conflict(raw, db_name)
                # 剥离非 ORM 列字段
                instance = orm_model(**raw)
                await mgr.insert(instance)
                success_ids.append(instance.id)
            except IntegrityError as e:
                failures.append(
                    {
                        "index": i,
                        "key": self._extract_conflict_key(e, raw),
                        "error": self._format_integrity_error(e, raw, orm_model),
                    }
                )
            except (TypeError, AttributeError, OperationalError) as e:
                logger.exception("批量插入第 %d 条 %s 失败", i, orm_model.__tablename__)
                key = {
                    k: (v if isinstance(v, str) else str(v)) if v is not None else ""
                    for k, v in raw.items()
                    if k.endswith(("_code", "_date")) and v is not None
                }
                failures.append({"index": i, "key": key, "error": str(e)})

        sc, fc = len(success_ids), len(failures)
        if fc == 0:
            return UtilResponse(
                code=Errcode.SUCCESS,
                message="批量添加成功",
                data={
                    "success_count": sc,
                    "fail_count": 0,
                    "ids": success_ids,
                    "failures": [],
                },
            )
        if sc == 0:
            return UtilResponse(
                code=Errcode.FAIL,
                message=f"全部{fc}条失败",
                data={
                    "success_count": 0,
                    "fail_count": fc,
                    "ids": [],
                    "failures": failures,
                },
            )
        return UtilResponse(
            code=Errcode.SUCCESS,
            message=f"成功{sc}条，失败{fc}条",
            data={
                "success_count": sc,
                "fail_count": fc,
                "ids": success_ids,
                "failures": failures,
            },
        )
