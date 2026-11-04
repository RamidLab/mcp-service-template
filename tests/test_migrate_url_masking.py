"""迁移脚本不许把数据库口令打印出来。

起因是同族仓库的一次实机预演：脚本头一行打成
`postgresql+asyncpg://postgres:<口令>@<主机>:5432/<库名>`，而预演是**只读**动作——正因为只读，
人才会放松地去截屏、贴日志、转进会话记录，泄露面比写库那一步还宽。

判据只看两件事：任何**带口令的 URL** 折进掩码之后，口令本身一个字符都不许留在输出里；
同时方言/用户/主机/库名要原样留着（那是运维判断"我连的是哪台库"所需的信息，遮掉就等于自废）。
另有一条扫源用例：只修"这次跑到的那一个脚本"等于把同一个陷阱留给下一个运维。
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any


_COMMON_PATH = Path(__file__).resolve().parent.parent / "scripts" / "_migration_common.py"


def _common() -> Any:
    """按路径加载迁移脚本公共模块（scripts/ 不在包里，与被测脚本自身的加载方式一致）。"""
    spec = importlib.util.spec_from_file_location("migration_common_for_test", _COMMON_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


masked_url = _common().masked_url


def test_password_is_gone_but_the_target_is_readable() -> None:
    out = masked_url("postgresql+asyncpg://postgres:S3cr3t-§h@192.168.1.37:5432/service_data")

    assert "S3cr3t" not in out, out
    assert "§h" not in out, out
    assert "192.168.1.37" in out, out
    assert "service_data" in out, out
    assert "postgresql" in out, out


def test_user_name_is_kept() -> None:
    """用户名不是秘密，运维要靠它区分"哪个角色连的库"（本地/只读账号一眼可辨）；遮的只是口令。"""
    out = masked_url("postgresql+asyncpg://postgres:pw@localhost:5432/service_data")

    assert "://postgres:***@" in out, out
    assert "pw@" not in out, out


def test_url_without_password_is_passed_through_unchanged() -> None:
    url = "sqlite+aiosqlite:///D:/Person/Code/admin-platform-template/service_data.db"

    assert masked_url(url) == url


def test_tcp_url_without_userinfo_is_kept() -> None:
    """没有 userinfo 的 DSN 不该被折出 `***` —— 那会让人误以为这里藏着一个口令。"""
    url = "postgresql+asyncpg://192.168.1.37:5432/service_data"

    assert masked_url(url) == url
    assert "***" not in masked_url(url)


def test_percent_encoded_password_is_fully_masked() -> None:
    """口令里带 `%`（URL 转义）是最常见的写法，必须整段遮掉，不能只遮到第一个 `%` 之前。"""
    out = masked_url("postgresql+asyncpg://postgres:a%40b%23c@192.168.1.37:5432/service_data")

    assert "a%40b%23c" not in out, out
    assert "192.168.1.37" in out, out
    assert "service_data" in out, out


def test_non_url_string_is_returned_unchanged_without_raising() -> None:
    """认不出的串原样交回、不抛异常。

    这里刻意**不**假装能挡住任意文本：本函数的输入面只有带 driver 的 DSN（`DBManager` 就吃这个），
    一段随便的中文/日志行不是它的输入，为一个不存在的输入面编造"什么都遮"的防护只会把
    运维真正要看的方言与主机也遮掉。
    """
    text = "预演结束：本次未写入，待执行动作 2 项"

    assert masked_url(text) == text


def test_no_script_prints_a_raw_dsn() -> None:
    """所有迁移脚本的 DSN 出口都必须过 `masked_url`。

    只修"这次跑到的那一个脚本"等于把同一个陷阱留给下一个运维——所以这条直接扫 `scripts/*.py`，
    列出每一处把 `{url}` 原样打进 print 却没遮罩的行。
    """
    offenders: list[str] = []
    for path in sorted(_COMMON_PATH.parent.glob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "{url}" in line and "print" in line and "masked_url" not in line:
                offenders.append(f"{path.name}:{number}")

    assert not offenders, f"这些行会把带口令的 DSN 原样打出去：{offenders}"
