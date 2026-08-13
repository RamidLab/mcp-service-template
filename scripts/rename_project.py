"""项目改名脚本 —— 将模板占位符一键替换为你的项目名。

模板使用占位符命名（service_mcp / service-mcp / "Service MCP" / service_data / SM_）。
本脚本遍历仓库内所有文本文件执行内容替换，并将包目录 service_mcp/ 重命名。

用法:
    uv run python scripts/rename_project.py my_company \\
        --project my-company-mcp --display "My Company MCP" --db my_company_data
    uv run python scripts/rename_project.py my_company --dry-run   # 预览

参数:
    NEW_PACKAGE_NAME  必需。新的 Python 包名（如 my_company，须为合法标识符）
    --project        项目名（连字符形式），默认 = 包名中下划线转连字符
    --display        服务显示名，默认 = 包名 Title Case
    --db             默认数据库名，默认 = --project 的下划线形式
    --perm-prefix    权限码前缀，默认保留 SM_
    --dry-run        仅打印将执行的操作，不写入

注意:
    - uv.lock 不参与替换，请运行 `uv sync` 重新生成
    - 重命名包后如提示 stub 过期，运行 `uv run python scripts/refresh_project_stub.py`
    - 只改名（不换实体）时无需改动其他内容
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = PROJECT_ROOT / "service_mcp"

# 遍历时跳过的目录
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".mimocode",
    "dist",
    "logs",
    "data",
    "dev_data",
    "node_modules",
    ".cache",
}
# 跳过不参与内容替换的文件
SKIP_FILES = {"uv.lock", ".prefab_compat_version"}

IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="项目改名脚本")
    parser.add_argument("package", help="新的 Python 包名（如 my_company）")
    parser.add_argument("--project", default=None, help="项目名（连字符形式）")
    parser.add_argument("--display", default=None, help="服务显示名（如 My Company MCP）")
    parser.add_argument("--db", default=None, help="默认数据库名（如 my_company_data）")
    parser.add_argument("--perm-prefix", default=None, help="权限码前缀（默认保留 SM_）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not IDENT_RE.match(args.package):
        print(f"✗ 包名 '{args.package}' 不合法：须为 ^[a-z_][a-z0-9_]*$", file=sys.stderr)
        return 1

    package = args.package
    project = args.project or package.replace("_", "-")
    display = args.display or package.replace("_", " ").title()
    db_name = args.db or project.replace("-", "_")
    perm_prefix = args.perm_prefix or "SM_"

    # 替换表（长 token 优先，避免部分覆盖）
    replacements = [
        ("Service MCP", display),
        ("service-mcp", project),
        ("service_mcp", package),
        ("service_data", db_name),
    ]
    if args.perm_prefix is not None:
        replacements.append(("SM_", perm_prefix))

    # 未提交改动检查
    git_dir = PROJECT_ROOT / ".git"
    if git_dir.exists():
        import subprocess

        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        if status.stdout.strip():
            print(
                "⚠ 工作区存在未提交的改动。建议先提交或 stash 再执行改名。"
                "如需强制继续，请先提交后重试。",
                file=sys.stderr,
            )
            return 1

    if not PACKAGE_DIR.exists():
        print(f"✗ 找不到包目录 {PACKAGE_DIR}", file=sys.stderr)
        return 1

    print(f"目标: 包名={package}  项目名={project}  显示名={display}  数据库名={db_name}")
    print(f"权限前缀={perm_prefix}  模式={'dry-run（不写入）' if args.dry_run else '写入'}\n")

    # 1. 内容替换
    changed_files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_FILES:
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as f:
                    raw = f.read()
            except OSError:
                continue
            if b"\x00" in raw:
                continue  # 二进制文件跳过
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            new = text
            for old, new_tok in replacements:
                new = new.replace(old, new_tok)
            if new != text:
                changed_files.append(os.path.relpath(path, PROJECT_ROOT))
                if not args.dry_run:
                    with open(path, "w", encoding="utf-8", newline="") as f:
                        f.write(new)

    # 2. 包目录重命名
    target_dir = PROJECT_ROOT / package
    dir_action = f"重命名目录 service_mcp/ → {package}/"
    if args.dry_run:
        print(f"  [dir ] {dir_action}")
    else:
        if target_dir.exists():
            print(f"✗ 目标目录 {target_dir} 已存在，中止。", file=sys.stderr)
            return 1
        if package.lower() == "service_mcp" and package != "service_mcp":
            # 大小写仅变的改名在 Windows/macOS 上需临时名中转
            tmp = PROJECT_ROOT / (package + ".tmp")
            PACKAGE_DIR.rename(tmp)
            tmp.rename(target_dir)
        else:
            PACKAGE_DIR.rename(target_dir)
        print(f"  [dir ] {dir_action}")

    for rel in changed_files:
        print(f"  [file] {rel}")
    print(f"\n共替换 {len(changed_files)} 个文件")

    if not args.dry_run:
        print("\n下一步:")
        print("  1. uv sync        # 重新生成 uv.lock 并安装")
        print("  2. uv run pytest  # 确认测试通过")
        print("  3. uv run python scripts/refresh_project_stub.py  # 如需刷新 .pyi stub")
    return 0


if __name__ == "__main__":
    sys.exit(main())
