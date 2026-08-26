"""大结果溢出。

MCP 工具返回超大响应时，将结果原子写入私有临时文件并返回 (路径, sha256, 字节数)，
避免单次调用拖垮服务；启动时清扫过期文件防止磁盘膨胀。

用法：
    path, digest, size = LargeResultWriter().write("export", {"rows": [...]})
"""

__all__ = ["LargeResultWriter", "spill_dir", "sweep_spill_dir"]

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from service_mcp.utils.log import get_logger
from service_mcp.utils.path_utils import PROJECT_ROOT


logger = get_logger(__name__)

DEFAULT_SPILL_DIR = PROJECT_ROOT / ".cache" / "spill"
DEFAULT_LIFETIME_HOURS = 24
MAX_FILES = 100


def spill_dir() -> Path:
    """溢出目录（相对项目根 .cache/spill）。"""
    path = DEFAULT_SPILL_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


class LargeResultWriter:
    """将超限响应原子写入私有文件（0600），返回 (路径, sha256, 字节数)。"""

    def __init__(self, directory: Path | None = None, lifetime_hours: int = DEFAULT_LIFETIME_HOURS):
        self.directory = directory or spill_dir()
        self.lifetime_hours = lifetime_hours

    def write(self, tag: str, payload: dict) -> tuple[str, str, int]:
        """写入 JSON 载荷，返回 (absolute_path, sha256_hex, byte_count)。

        Args:
            tag: 业务标识（账号名 / 导出名等），用于文件名可读性。
            payload: 待写入的 JSON 载荷。
        """
        data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        filename = f"spill_{tag}_{stamp}_{secrets.token_hex(8)}.json"
        final = self.directory / filename
        tmp = self.directory / f".{filename}.tmp"

        digest = hashlib.sha256()
        with open(tmp, "wb") as f:
            f.write(data)
            digest.update(data)
        os.replace(tmp, final)
        if os.name != "nt":
            try:
                os.chmod(final, 0o600)
            except OSError:
                pass
        logger.info(f"响应溢出到文件: {final} ({len(data)} bytes)")
        return str(final), digest.hexdigest(), len(data)


def sweep_spill_dir(
    directory: Path | None = None, lifetime_hours: int = DEFAULT_LIFETIME_HOURS
) -> int:
    """启动时清扫溢出目录：删除超期文件，再按数量上限清理最旧文件。返回删除数。"""
    directory = directory or spill_dir()
    removed = 0
    cutoff = datetime.now(UTC) - timedelta(hours=lifetime_hours)

    def _mtime(path: Path) -> datetime:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            return datetime.min.replace(tzinfo=UTC)

    files = [p for p in directory.glob("spill_*.json") if p.is_file()]
    for path in files:
        if _mtime(path) < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    files = [p for p in directory.glob("spill_*.json") if p.is_file()]
    files.sort(key=_mtime)
    while len(files) > MAX_FILES:
        try:
            files.pop(0).unlink()
            removed += 1
        except OSError:
            break
    if removed:
        logger.info(f"清扫溢出目录，删除 {removed} 个过期文件")
    return removed
