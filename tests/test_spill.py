"""测试大结果溢出（utils/spill.py）"""

import json
import os
import time
from pathlib import Path

from service_mcp.utils.spill import LargeResultWriter, sweep_spill_dir


def test_write_returns_path_digest_size(tmp_path: Path):
    writer = LargeResultWriter(directory=tmp_path)
    path, digest, size = writer.write("test", {"rows": [1, 2, 3], "name": "产品A"})

    assert Path(path).exists()
    assert Path(path).parent == tmp_path
    assert digest == _sha256_of(Path(path))
    assert size == Path(path).stat().st_size

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert payload == {"rows": [1, 2, 3], "name": "产品A"}


def test_write_atomic_no_tmp_left(tmp_path: Path):
    writer = LargeResultWriter(directory=tmp_path)
    writer.write("t", {"a": 1})
    leftovers = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_sweep_removes_expired(tmp_path: Path):
    writer = LargeResultWriter(directory=tmp_path)
    writer.write("t1", {"a": 1})
    writer.write("t2", {"a": 2})

    # 将文件 mtime 拨到过去
    old = time.time() - 3600 * 48
    for p in tmp_path.iterdir():
        if p.name.startswith("spill_"):
            os.utime(p, (old, old))

    removed = sweep_spill_dir(directory=tmp_path, lifetime_hours=24)
    assert removed == 2
    assert list(tmp_path.glob("spill_*.json")) == []


def test_sweep_keeps_fresh(tmp_path: Path):
    writer = LargeResultWriter(directory=tmp_path)
    writer.write("t1", {"a": 1})
    removed = sweep_spill_dir(directory=tmp_path, lifetime_hours=24)
    assert removed == 0
    assert len(list(tmp_path.glob("spill_*.json"))) == 1


def _sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()
