import json
import logging

import pytest

from service_mcp.utils.log import configure_logging, get_log_level, get_logger


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
