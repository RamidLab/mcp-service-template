"""测试 cron 表达式解析（utils/cron.py）"""

from datetime import datetime

import pytest

from service_mcp.utils.cron import CronExpression


def test_parse_star():
    cron = CronExpression("* * * * *")
    assert cron.minute == list(range(60))
    assert cron.hour == list(range(24))
    assert cron.weekday == list(range(7))


def test_parse_step():
    cron = CronExpression("*/15 * * * *")
    assert cron.minute == list(range(0, 60, 15))


def test_parse_range():
    cron = CronExpression("0 9-17 * * 1-5")
    assert cron.hour == list(range(9, 18))
    assert cron.weekday == list(range(1, 6))


def test_parse_single():
    cron = CronExpression("30 9 * * 1")
    assert cron.minute == [30]
    assert cron.hour == [9]
    assert cron.weekday == [1]


def test_invalid_expression():
    with pytest.raises(ValueError):
        CronExpression("not-a-cron")
    with pytest.raises(ValueError):
        CronExpression("0 9 * *")


def test_next_run_same_day():
    cron = CronExpression("30 9 * * *")
    nxt = cron.next_run(datetime(2026, 1, 1, 8, 0))
    assert nxt == datetime(2026, 1, 1, 9, 30)


def test_next_run_next_day():
    cron = CronExpression("30 9 * * *")
    nxt = cron.next_run(datetime(2026, 1, 1, 10, 0))
    assert nxt == datetime(2026, 1, 2, 9, 30)


def test_next_run_weekday():
    # 本实现以 datetime.weekday() 为准：0=周一 … 6=周日，字段 1 → 周二
    # 2026-01-06 是周二；当天 12:00 命中
    cron = CronExpression("0 12 * * 1")
    nxt = cron.next_run(datetime(2026, 1, 6, 0, 0))
    assert nxt == datetime(2026, 1, 6, 12, 0)


def test_next_run_beyond_24h_window():
    # 简单实现只往后查 24 小时（已知限制）
    cron = CronExpression("0 12 * * 1")  # 周二
    with pytest.raises(ValueError):
        cron.next_run(datetime(2026, 1, 5, 0, 0))  # 周一，下一个周二超出窗口
