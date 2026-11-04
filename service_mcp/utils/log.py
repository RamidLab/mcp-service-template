from __future__ import annotations


__all__ = ["configure_logging", "demote_console_rendering", "get_log_level", "get_logger"]

import datetime
import json
import logging
import logging.handlers
import sys
import traceback
from typing import Any

from rich.logging import RichHandler

from service_mcp.utils.path_utils import PROJECT_ROOT


#: 非 tty 时的控制台格式：一行一条、可 grep（rich 会把一行拆成带边框的多行并按列宽折行）
PLAIN_CONSOLE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def _is_interactive() -> bool:
    """标准输出是不是终端。重定向到文件/管道时不是——那是日志的正常落法。"""
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _plain_console_handler() -> logging.Handler:
    """纯文本控制台处理器：一行一条，落进文件/管道后仍可按行 grep。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(PLAIN_CONSOLE_FORMAT))
    return handler


def _console_handler() -> logging.Handler:
    """tty 用 rich，非 tty 用纯文本流处理器。"""
    if _is_interactive():
        return RichHandler(rich_tracebacks=True, show_path=False)
    return _plain_console_handler()


def demote_console_rendering(name: str = "fastmcp") -> int:
    """把某个 logger 自带的 rich 控制台处理器换成纯文本，返回换掉的个数（tty 下不换，回 0）。

    第三方库（FastMCP）在自己的模块被 import 时就把日志配好了，而 `configure_logging`
    只清 root 的处理器，管不到那一层——不换的话它那一路输出仍然是折行 + 边框格式。
    """
    if _is_interactive():
        return 0
    target = logging.getLogger(name)
    replaced = 0
    for handler in list(getattr(target, "handlers", ())):
        if type(handler).__module__.startswith("rich"):
            target.removeHandler(handler)
            plain = _plain_console_handler()
            plain.setLevel(handler.level)
            target.addHandler(plain)
            handler.close()
            replaced += 1
    return replaced


def get_logger(name: str | None = None) -> logging.Logger:
    """获取日志记录器。

    返回标准 logging.Logger，向 root logger 传播，由 configure_logging 统一配置输出。
    """
    return logging.getLogger(name or "service_mcp")


class JSONFormatter(logging.Formatter):
    """将日志记录格式化为单行 JSON，用于生产环境文件落盘。"""

    def format(self, record: logging.LogRecord) -> str:
        dt = datetime.datetime.fromtimestamp(record.created, tz=datetime.UTC)
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z"

        log_entry: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "path": record.pathname,
            "process": record.process,
            "thread": record.thread,
        }
        if record.exc_info:
            log_entry["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(log_entry, default=str, ensure_ascii=False)


class _MaxLevelFilter(logging.Filter):
    """只放行不高于指定级别的记录（用于把普通日志与错误日志分离）。"""

    def __init__(self, max_level: int) -> None:
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def _apply_library_log_levels() -> None:
    """从 configs/log_libraries.json 读取第三方库日志级别并应用。"""
    config_file = PROJECT_ROOT / "configs" / "log_libraries.json"
    if not config_file.exists():
        return

    # noinspection PyBroadException
    try:
        lib_config = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        return

    for lib_name, level_str in lib_config.items():
        if not isinstance(level_str, str):
            continue
        level = logging.getLevelNamesMapping().get(level_str.upper())
        if level is None:
            continue
        logging.getLogger(lib_name).setLevel(level)


def _make_file_handler(
    file_path: str,
    base_name: str,
    level: int,
    max_bytes: int,
    backup_count: int,
    json_format: bool,
    add_filter: logging.Filter | None = None,
) -> logging.Handler:
    from pathlib import Path

    log_dir = Path(file_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    handler: logging.Handler = logging.handlers.RotatingFileHandler(
        log_dir / f"{base_name}.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    formatter: logging.Formatter = (
        JSONFormatter()
        if json_format
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s:%(lineno)d - %(message)s")
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    if add_filter:
        handler.addFilter(add_filter)
    return handler


def configure_logging(
    level: int = logging.INFO,
    console: bool = True,
    file: bool = False,
    file_path: str = "logs",
    file_base_name: str = "service_mcp",
    backup_count: int = 100,
    max_file_size: int = 100 * 1024 * 1024,
    json_format: bool = True,
    separate_error_file: bool = False,
    error_file_base_name: str | None = None,
) -> None:
    """配置全局日志系统（可重复调用，每次先清空 root 处理器）。

    Args:
        level: 日志级别，使用 logging.DEBUG/INFO/WARNING/ERROR/CRITICAL。
        console: 是否输出到控制台（tty 用 rich，重定向到文件/管道时用一行一条的纯文本）。
        file: 是否输出到文件。
        file_path: 日志文件存放目录。
        file_base_name: 日志文件基名。
        backup_count: 文件滚动保留数量。
        max_file_size: 单文件最大字节数，超限后滚动。
        json_format: 文件输出是否使用 JSON 格式。
        separate_error_file: 是否将 ERROR 及以上级别分离到单独文件。
        error_file_base_name: 错误日志文件基名，默认在 file_base_name 后加 "_error"。
    """
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()

    root.setLevel(level)
    root.propagate = False

    if console:
        console_handler: logging.Handler = _console_handler()
        console_handler.setLevel(level)
        root.addHandler(console_handler)

    if file:
        if separate_error_file:
            info_level = level if level <= logging.WARNING else logging.WARNING
            root.addHandler(
                _make_file_handler(
                    file_path,
                    file_base_name,
                    info_level,
                    max_file_size,
                    backup_count,
                    json_format,
                    add_filter=_MaxLevelFilter(logging.WARNING),
                )
            )
            error_level = max(level, logging.ERROR)
            root.addHandler(
                _make_file_handler(
                    file_path,
                    error_file_base_name or f"{file_base_name}_error",
                    error_level,
                    max_file_size,
                    backup_count,
                    json_format,
                )
            )
        else:
            root.addHandler(
                _make_file_handler(
                    file_path,
                    file_base_name,
                    level,
                    max_file_size,
                    backup_count,
                    json_format,
                )
            )

    _apply_library_log_levels()


def get_log_level() -> int:
    """获取当前 root logger 级别。"""
    return logging.getLogger().level
