"""cron 表达式解析。

支持标准 5 段 cron：分 时 日 月 星期；字段支持 `*`、`*/step`、`a-b`、单值。
"""

from __future__ import annotations

from datetime import datetime, timedelta


__all__ = ["CronExpression"]


class CronExpression:
    """标准 5 段 cron 表达式解析器。

    Usage:
        cron = CronExpression("*/5 * * * *")
        next_time = cron.next_run()
    """

    def __init__(self, expression: str):
        self.expression = expression
        self._parse(expression)

    def _parse(self, expression: str) -> None:
        """解析 cron 表达式（分 时 日 月 星期）。"""
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")

        self.minute = self._parse_field(parts[0], 0, 59)
        self.hour = self._parse_field(parts[1], 0, 23)
        self.day = self._parse_field(parts[2], 1, 31)
        self.month = self._parse_field(parts[3], 1, 12)
        self.weekday = self._parse_field(parts[4], 0, 6)

    def _parse_field(self, field: str, min_val: int, max_val: int) -> list[int]:
        """解析单个 cron 字段。"""
        if field == "*":
            return list(range(min_val, max_val + 1))

        if "/" in field:
            base, step_str = field.split("/")
            step = int(step_str)
            if base == "*":
                return list(range(min_val, max_val + 1, step))
            start_val = int(base)
            return list(range(start_val, max_val + 1, step))

        if "-" in field:
            start_str, end_str = field.split("-")
            return list(range(int(start_str), int(end_str) + 1))

        return [int(field)]

    def next_run(self, after: datetime | None = None) -> datetime:
        """计算给定时间之后的下一次运行时间。"""
        if after is None:
            after = datetime.now()

        current = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)

        for _ in range(1440):  # 最多往后查 24 小时
            if (
                current.minute in self.minute
                and current.hour in self.hour
                and current.day in self.day
                and current.month in self.month
                and current.weekday() in self.weekday
            ):
                return current
            current += timedelta(minutes=1)

        raise ValueError(f"Could not find next run time for cron: {self.expression}")
