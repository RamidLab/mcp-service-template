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
