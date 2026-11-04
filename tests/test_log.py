import json
import logging
import sys

import pytest
from rich.logging import RichHandler

from service_mcp.utils.log import (
    configure_logging,
    demote_console_rendering,
    get_log_level,
    get_logger,
)


@pytest.fixture(autouse=True)
def reset_logging():
    """每个测试前清空 root logger 的处理器，测试后关闭。"""
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()
    root.setLevel(logging.WARNING)
    yield
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()


@pytest.fixture
def temp_log_dir(tmp_path):
    """临时目录，用于存放测试中生成的日志文件。"""
    return tmp_path / "logs"


def test_get_logger_name():
    """get_logger 返回标准 Logger，且名称正确。"""
    logger = get_logger("custom.name")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "custom.name"


def test_get_logger_default():
    """get_logger 无参时默认名为 service_mcp。"""
    assert get_logger().name == "service_mcp"


def test_file_logging(temp_log_dir):
    """文件模式下各级别消息写入同一文件。"""
    configure_logging(
        level=logging.DEBUG,
        console=False,
        file=True,
        file_path=str(temp_log_dir),
        file_base_name="test_basic_file",
        json_format=False,
    )
    logger = get_logger("test_basic")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")

    log_file = temp_log_dir / "test_basic_file.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "DEBUG" in content
    assert "INFO" in content
    assert "WARNING" in content
    assert "ERROR" in content
    assert "test_basic" in content


def test_file_logging_json(temp_log_dir):
    """JSON 格式文件日志包含 timestamp/level/message/logger 字段。"""
    configure_logging(
        level=logging.INFO,
        console=False,
        file=True,
        file_path=str(temp_log_dir),
        file_base_name="test_file_json",
        json_format=True,
    )
    get_logger("test_file_json").info("Hello file")

    log_file = temp_log_dir / "test_file_json.log"
    content = log_file.read_text(encoding="utf-8").strip()
    assert content
    record = json.loads(content)
    assert record["level"] == "INFO"
    assert record["message"] == "Hello file"
    assert record["logger"] == "test_file_json"
    assert "timestamp" in record


def test_separate_error_file(temp_log_dir):
    """错误日志分离：普通文件不含 ERROR，错误文件含 ERROR。"""
    configure_logging(
        level=logging.INFO,
        console=False,
        file=True,
        file_path=str(temp_log_dir),
        file_base_name="test_separate",
        json_format=False,
        separate_error_file=True,
        error_file_base_name="test_separate_error",
    )
    logger = get_logger("test_separate")
    logger.info("Info message")
    logger.error("Error message")

    assert (temp_log_dir / "test_separate.log").exists()
    assert (temp_log_dir / "test_separate_error.log").exists()
    normal = (temp_log_dir / "test_separate.log").read_text(encoding="utf-8")
    error = (temp_log_dir / "test_separate_error.log").read_text(encoding="utf-8")
    assert "Info message" in normal
    assert "Error message" not in normal
    assert "Error message" in error


def test_exception_logging(temp_log_dir):
    """logger.exception 输出完整异常堆栈。"""
    configure_logging(
        level=logging.ERROR,
        console=False,
        file=True,
        file_path=str(temp_log_dir),
        file_base_name="test_exc",
        json_format=False,
    )
    logger = get_logger("test_exc")
    try:
        raise ValueError("Test exception message")
    except ValueError:
        logger.exception("An error occurred")

    content = (temp_log_dir / "test_exc.log").read_text(encoding="utf-8")
    assert "An error occurred" in content
    assert "ValueError: Test exception message" in content


def test_get_log_level():
    """get_log_level 返回当前 root logger 级别。"""
    configure_logging(level=logging.INFO, console=False, file=False)
    assert get_log_level() == logging.INFO


def test_reconfigure_idempotent(temp_log_dir):
    """重复调用 configure_logging 会清空旧处理器，避免重复输出。"""
    configure_logging(level=logging.INFO, console=False, file=False)
    configure_logging(
        level=logging.DEBUG,
        console=False,
        file=True,
        file_path=str(temp_log_dir),
        file_base_name="test_reconfigure",
        json_format=False,
    )
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert get_log_level() == logging.DEBUG


def _plain_console_handlers(root: logging.Logger) -> list[logging.Handler]:
    return [
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]


def test_console_handler_is_plain_when_stdout_is_redirected():
    """重定向到文件/管道时不该用 rich：它把一行拆成带边框的多行并按列宽折行，grep 当场失效。"""
    original = sys.stdout.isatty
    sys.stdout.isatty = lambda: False  # type: ignore[method-assign]
    try:
        configure_logging(level=logging.INFO, console=True, file=False)
    finally:
        sys.stdout.isatty = original  # type: ignore[method-assign]

    root = logging.getLogger()
    assert not any(type(h).__module__.startswith("rich") for h in root.handlers), root.handlers
    consoles = _plain_console_handlers(root)
    assert len(consoles) == 1
    assert consoles[0].formatter is not None


def test_console_handler_stays_rich_on_a_terminal():
    """交互终端上 rich 是想要的（彩色、可读的 traceback），不该被顺手关掉。"""
    original = sys.stdout.isatty
    sys.stdout.isatty = lambda: True  # type: ignore[method-assign]
    try:
        configure_logging(level=logging.INFO, console=True, file=False)
    finally:
        sys.stdout.isatty = original  # type: ignore[method-assign]

    root = logging.getLogger()
    assert any(isinstance(h, RichHandler) for h in root.handlers), root.handlers


def test_demote_console_rendering_replaces_rich_and_keeps_level():
    logger = logging.getLogger("demote_probe")
    original = sys.stdout.isatty
    rich_handler = RichHandler(rich_tracebacks=True, show_path=False)
    rich_handler.setLevel(logging.WARNING)
    logger.handlers = [rich_handler]
    sys.stdout.isatty = lambda: False  # type: ignore[method-assign]
    try:
        replaced = demote_console_rendering("demote_probe")
        handlers = list(logger.handlers)
    finally:
        sys.stdout.isatty = original  # type: ignore[method-assign]
        for handler in logger.handlers:
            handler.close()
        logger.handlers = []

    assert replaced == 1
    assert handlers
    assert not any(isinstance(h, RichHandler) for h in handlers), handlers
    assert handlers[0].level == logging.WARNING


def test_demote_console_rendering_leaves_plain_handlers_alone():
    logger = logging.getLogger("demote_probe_plain")
    keep = logging.StreamHandler(sys.stdout)
    logger.handlers = [keep]
    original = sys.stdout.isatty
    sys.stdout.isatty = lambda: False  # type: ignore[method-assign]
    try:
        replaced = demote_console_rendering("demote_probe_plain")
        handlers = list(logger.handlers)
    finally:
        sys.stdout.isatty = original  # type: ignore[method-assign]
        logger.handlers = []

    assert replaced == 0
    assert handlers == [keep]


def test_demote_console_rendering_is_noop_on_a_terminal():
    logger = logging.getLogger("demote_probe_tty")
    rich_handler = RichHandler(show_path=False)
    logger.handlers = [rich_handler]
    original = sys.stdout.isatty
    sys.stdout.isatty = lambda: True  # type: ignore[method-assign]
    try:
        replaced = demote_console_rendering("demote_probe_tty")
        stayed = logger.handlers == [rich_handler]
    finally:
        sys.stdout.isatty = original  # type: ignore[method-assign]
        logger.handlers = []
        rich_handler.close()

    assert replaced == 0
    assert stayed
