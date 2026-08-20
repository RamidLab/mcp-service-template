import logging
import os
import sys
from pathlib import Path
from typing import cast

import typer
from fastmcp import FastMCP
from fastmcp import settings as fastmcp_settings
from fastmcp.server.middleware.logging import StructuredLoggingMiddleware
from fastmcp.server.middleware.timing import TimingMiddleware
from fastmcp.server.providers import FileSystemProvider
from fastmcp.settings import LOG_LEVEL
from fastmcp.utilities.logging import configure_logging as fastmcp_configure_logging
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from service_mcp.apps.config_app import config_app
from service_mcp.auth.config import AuthConfig
from service_mcp.auth.discovery import (
    get_all_permissions,
    get_entity_metadata,
)
from service_mcp.auth.middleware import JWTAuthMiddleware
from service_mcp.config import setup_settings
from service_mcp.utils.log import configure_logging, get_logger
from service_mcp.utils.path_utils import load_env


logger = get_logger(__name__)


# ── 初始化配置与日志 ──

# 脚本方式运行（python server.py / uv run --script）时不会先执行 service_mcp 包 __init__，
# 而 fastmcp 在 import 时已按默认级别（INFO）配置好日志；此处重新加载环境变量并同步级别。
load_env()
fastmcp_settings.log_level = cast(LOG_LEVEL, os.getenv("FASTMCP_LOG_LEVEL", "INFO"))
fastmcp_configure_logging(level=fastmcp_settings.log_level, logger=logging.getLogger("fastmcp"))
# 屏蔽 uvicorn/httpx/httpcore 的请求日志
for _name in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore", "aiohttp"):
    logging.getLogger(_name).setLevel(logging.WARNING)

app_settings = setup_settings()
_log_cfg = app_settings.logging
configure_logging(
    level=logging.getLevelNamesMapping()[fastmcp_settings.log_level],
    console=_log_cfg.console,
    file=_log_cfg.file,
    file_path=_log_cfg.file_path,
    file_base_name=_log_cfg.file_base_name,
    backup_count=_log_cfg.backup_count,
    max_file_size=_log_cfg.max_file_size,
    json_format=_log_cfg.json_format,
    separate_error_file=_log_cfg.separate_error_file,
    error_file_base_name=_log_cfg.error_file_base_name,
)

auth_config = AuthConfig.from_env()

# 预加载实体元数据缓存
get_entity_metadata()


# ── MCP Server ──

mcp = FastMCP(
    "Service MCP",
    providers=[
        FileSystemProvider(str(Path(__file__).parent / "tools")),
        config_app,
    ],
    middleware=[
        StructuredLoggingMiddleware(
            include_payloads=_log_cfg.include_payloads,
            include_payload_length=_log_cfg.include_payload_length,
            estimate_payload_tokens=_log_cfg.estimate_payload_tokens,
            methods=_log_cfg.methods,
        ),
        TimingMiddleware(),
    ],
)


@mcp.custom_route("/permissions", methods=["GET"])
async def list_permissions(_request: Request):
    perms = get_all_permissions()
    return JSONResponse({"code": 0, "message": "ok", "data": perms})


cli = typer.Typer()


def _get_http_middleware() -> list[Middleware]:
    if auth_config.mode == "admin":

        def _create(app: ASGIApp) -> JWTAuthMiddleware:
            return JWTAuthMiddleware(app, config=auth_config)

        return [Middleware(_create)]
    return []


@cli.command()
def stdio():
    """以 stdio 模式运行服务器"""
    mcp.run(transport="stdio")


@cli.command()
def sse(
    host: str = typer.Option("127.0.0.1", envvar="MCP_HOST"),
    port: int = typer.Option(8001, envvar="MCP_PORT"),
):
    """以 SSE 模式运行服务器"""
    mcp.run(transport="sse", host=host, port=port, middleware=_get_http_middleware())


@cli.command()
def streamable_http(
    host: str = typer.Option("127.0.0.1", envvar="MCP_HOST"),
    port: int = typer.Option(8001, envvar="MCP_PORT"),
):
    """以 streamable-http 模式运行服务器"""
    import signal as _signal

    def _on_signal(signum, _frame):
        logger.warning(f"收到信号 {signum}，正在退出...")
        raise SystemExit(0)

    _signal.signal(_signal.SIGTERM, _on_signal)
    _signal.signal(_signal.SIGINT, _on_signal)

    mcp.run(transport="streamable-http", host=host, port=port, middleware=_get_http_middleware())


@cli.command()
def ui(
    dev_port: int = typer.Option(8080, envvar="MCP_UI_PORT"),
    reload: bool = typer.Option(True, envvar="MCP_UI_RELOAD"),
    mcp_port: int = typer.Option(8001, envvar="MCP_PORT"),
):
    """以 UI 模式运行服务器（启动 Apps 预览界面）"""
    import subprocess

    subprocess.run(
        [
            "fastmcp",
            "dev",
            "apps",
            __file__,
            "--dev-port",
            str(dev_port),
            "--mcp-port",
            str(mcp_port),
            f"--{'reload' if reload else 'no-reload'}",
        ]
    )


if __name__ == "__main__":
    if len(sys.argv) == 1:
        cli([os.getenv("MCP_TRANSPORT", "stdio")])
    else:
        cli()
