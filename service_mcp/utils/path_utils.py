__all__ = ["PROJECT_ROOT", "get_config_path", "get_toml_config", "load_env"]

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def load_env():
    """
    根据 MCP_ENV 加载环境变量。
    """
    if (base_file := PROJECT_ROOT / ".env").exists():
        load_dotenv(base_file)

    if (specific_file := PROJECT_ROOT / f".env.{os.getenv('MCP_ENV', 'dev').lower()}").exists():
        load_dotenv(specific_file, override=True)

    if (local := PROJECT_ROOT / ".env.local").exists():
        load_dotenv(local, override=True)


def get_config_path() -> Path:
    return PROJECT_ROOT / "configs"


def get_toml_config(env: str | None = None) -> Path:
    """
    根据环境变量和本地覆盖确定最终配置文件路径。

    Args:
        env: 可选，指定环境名称（如 'dev', 'prod'），默认从 MCP_ENV 环境变量读取。

    Returns:
        配置文件路径。
    """
    config_dir = get_config_path()
    if env is None:
        env = os.getenv("MCP_ENV", "dev").lower()
    env_config_file = config_dir / f"config.{env}.toml"
    local_config_file = config_dir / "config.local.toml"
    custom_path = os.getenv("MCP_CONFIG_PATH")
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    if local_config_file.exists():
        return local_config_file
    return env_config_file
