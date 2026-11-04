from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class AuthConfig:
    mode: str = "tool"
    auth_api_url: str = "http://127.0.0.1:8000/api/auth/validate"
    bypass_paths: list[str] = field(default_factory=lambda: ["/permissions"])

    @classmethod
    def from_env(cls) -> AuthConfig:
        return cls(
            mode=os.getenv("MCP_AUTH_MODE", "tool"),
            auth_api_url=os.getenv("MCP_AUTH_API_URL", "http://127.0.0.1:8000/api/auth/validate"),
        )


def is_admin_mode() -> bool:
    """鉴权是否开启（admin 模式）：判"缺身份要不要拒"的唯一提问处。

    tool 模式没有身份概念，缺上下文按设计放行；admin 模式一旦缺上下文就必须 fail-closed。
    装饰器与写侧判据共用这一枚判断，避免两处各自读环境变量而分叉。
    """
    return AuthConfig.from_env().mode == "admin"
