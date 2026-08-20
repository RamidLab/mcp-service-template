"""敏感字段对称加密工具（Fernet）。

密钥来自配置 `MCP_ENCRYPTION_KEY`（Fernet base64 密钥，`Fernet.generate_key()` 生成）。
密文带 `enc:` 前缀；无前缀的值视为历史明文，直接透传（兼容已入库的明文数据）。
密钥缺失时加密退化为明文（不破坏行为），解密遇到密文但缺密钥则抛错。
"""

from __future__ import annotations


__all__ = ["decrypt_password", "encrypt_password"]

from cryptography.fernet import Fernet, InvalidToken


_PREFIX = "enc:"


def _cipher() -> Fernet | None:
    """从配置读取加密密钥构造 Fernet；未配置密钥时返回 None（明文兼容）。"""
    from service_mcp.config import get_settings

    key = get_settings().encryption_key
    if not key:
        return None
    return Fernet(key.get_secret_value().encode())


def encrypt_password(plaintext: str | None) -> str | None:
    """明文密码 → `enc:` 前缀密文；None/空串或未配置密钥时原样返回。"""
    if not plaintext:
        return plaintext
    cipher = _cipher()
    if cipher is None:
        return plaintext
    return _PREFIX + cipher.encrypt(plaintext.encode()).decode()


def decrypt_password(value: str | None) -> str:
    """`enc:` 前缀密文 → 明文；无前缀视为历史明文直接返回。"""
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value
    cipher = _cipher()
    if cipher is None:
        raise ValueError("缺少 MCP_ENCRYPTION_KEY，无法解密密码")
    try:
        return cipher.decrypt(value[len(_PREFIX) :].encode()).decode()
    except InvalidToken as e:
        raise ValueError("密码解密失败（密钥不匹配或密文损坏）") from e
