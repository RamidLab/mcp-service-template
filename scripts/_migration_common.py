"""迁移脚本公共基础设施。

`scripts/migrate_*.py` 共享的样板集中于此，避免每个脚本各抄一份、日后各自漂移。
新增迁移脚本请从这里 import，而不是把工具函数复制进脚本。
"""

from __future__ import annotations


def masked_url(url: str) -> str:
    """把 DSN 里的口令折成 `***`，其余原样保留。

    触发这条的是一次实机预演：脚本头一行打成
    `postgresql+asyncpg://postgres:<口令>@<主机>:5432/<库名>`，而预演是**只读**动作——正因为只读，
    人才会放松地去截屏、贴日志、转进会话记录，泄露面比写库那一步还宽。

    只按 URL 结构切（`scheme://user:pass@host/db`）。没有 `://`、没有 `@`、或只有用户没有口令的
    串一律原样交回：本函数的输入面是带 driver 的 DSN（`DBManager` 就吃这个），不是任意文本；
    为不存在的输入面编造"什么都遮"的防护，只会把运维真正要认的方言与主机一起遮掉。
    """
    scheme, sep, rest = url.partition("://")
    if not sep or "@" not in rest:
        return url
    userinfo, _, host_part = rest.rpartition("@")
    user, colon, _password = userinfo.partition(":")
    if not colon:
        return url
    return f"{scheme}://{user}:***@{host_part}"
