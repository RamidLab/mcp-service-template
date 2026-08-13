"""生成 prefab_ui 组件的类型兼容层 (prefab_compat.py)。

通过运行时 introspect prefab_ui 组件的 Pydantic model_fields，
自动生成带明确 __init__ 签名和上下文管理器协议的包装类。

用法: .venv/Scripts/python scripts/refresh_prefab_stub.py
"""

from __future__ import annotations

import inspect
import subprocess
import sys
import typing
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).parent.parent
COMPAT_FILE = PROJECT_ROOT / "service_mcp" / "apps" / "prefab_compat.py"


# ── 版本检测 ─────────────────────────────────────────────────────────────────


def _get_package_version() -> str:
    try:
        import prefab_ui

        return getattr(prefab_ui, "__version__", "unknown")
    except ImportError:
        return "not_installed"


def _check_version_changed() -> bool:
    version_file = COMPAT_FILE.parent / ".prefab_compat_version"
    current = _get_package_version()
    if version_file.exists():
        cached = version_file.read_text(encoding="utf-8").strip()
        if cached == current and COMPAT_FILE.exists():
            return False
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(current, encoding="utf-8")
    return True


# ── 类型格式化 ───────────────────────────────────────────────────────────────


def _format_type(tp: Any) -> str:
    """将类型对象格式化为可读字符串。"""
    if tp is type(None):
        return "None"
    if tp is Any:
        return "Any"

    # Annotated — 只取基础类型
    if hasattr(tp, "__metadata__") and tp.__metadata__:
        args = getattr(tp, "__args__", ())
        if args:
            return _format_type(args[0])

    origin = getattr(tp, "__origin__", None)
    if origin is not None:
        args = getattr(tp, "__args__", ())

        if origin is typing.Annotated:
            return _format_type(args[0])
        if origin is typing.Literal:
            literals = [f'"{a}"' if isinstance(a, str) else str(a) for a in args]
            return f"Literal[{', '.join(literals)}]"
        if origin is typing.Union or (
            hasattr(origin, "__name__") and origin.__name__ == "UnionType"
        ):
            return _format_union(args)
        if origin is type:
            return f"type[{_format_type(args[0])}]" if args else "type"

        origin_name = getattr(origin, "__qualname__", getattr(origin, "__name__", None)) or ""
        if origin_name:
            args_str = ", ".join(_format_type(a) for a in args)
            return f"{origin_name}[{args_str}]"

    if hasattr(tp, "__module__") and tp.__module__ == "builtins":
        return tp.__qualname__
    if hasattr(tp, "__qualname__"):
        return tp.__qualname__
    if hasattr(tp, "__name__"):
        return tp.__name__
    return str(tp)


def _format_union(args: tuple) -> str:
    parts = [_format_type(a) for a in args if a is not type(None)]
    if any(a is type(None) for a in args):
        parts.append("None")
    return " | ".join(dict.fromkeys(parts))


def _get_type_str(field_info: Any) -> str:
    annotation = field_info.annotation
    if annotation is None:
        return "Any"
    result = _format_type(annotation)
    for prefix in [
        "prefab_ui.rx.",
        "prefab_ui.actions.base.",
        "prefab_ui.actions.",
        "prefab_ui.css.",
        "prefab_ui.themes.base.",
        "prefab_ui.themes.",
        "prefab_ui.components.data_table.",
        "prefab_ui.components.",
        "prefab_ui.",
        "typing.",
    ]:
        result = result.replace(prefix, "")
    for utype in ["Responsive", "Theme", "ExpandableRow", "_TextComponent"]:
        result = result.replace(utype, "Any")
    return result


# ── 字段收集 ─────────────────────────────────────────────────────────────────


def _collect_fields(cls: type) -> dict[str, Any]:
    skip = {"type"}
    fields: dict[str, Any] = {}
    for ancestor in reversed(cls.__mro__):
        if hasattr(ancestor, "model_fields"):
            fields.update({n: fi for n, fi in ancestor.model_fields.items() if n not in skip})
    return fields


def _find_positional(cls: type) -> list[str]:
    try:
        sig = inspect.signature(cls.__init__)
    except (ValueError, TypeError):
        return []
    return [
        n
        for n, p in sig.parameters.items()
        if n not in ("self", "kwargs")
        and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]


def _simplify_param_type(type_str: str) -> str:
    """简化参数类型：移除 Literal，保留 Rx 等实际类型。"""
    parts = [p.strip() for p in type_str.split("|")]
    simplified = [p for p in parts if not p.startswith("Literal[")]
    # 如果移除了 Literal 但没有 str，加回 str
    if not any(p == "str" for p in simplified) and any(p.startswith("Literal[") for p in parts):
        simplified.append("str")
    return " | ".join(dict.fromkeys(simplified)) if simplified else "Any"


def _make_param(name: str, fi: Any) -> str:
    type_str = _simplify_param_type(_get_type_str(fi))
    default = fi.default
    has_none = "None" in type_str
    if default is None:
        return (
            f"    {name}: {type_str} = None,"
            if has_none
            else f"    {name}: {type_str} | None = None,"
        )
    if isinstance(default, bool):
        return f"    {name}: {type_str} = {default},"
    if isinstance(default, (int, float, str)):
        return f"    {name}: {type_str} = {default!r},"
    return (
        f"    {name}: {type_str} = None," if has_none else f"    {name}: {type_str} | None = None,"
    )


# ── 包装类生成 ───────────────────────────────────────────────────────────────


# 仅作为类型引用导入（不生成包装类）
_TYPE_ONLY = {"DataTableColumn"}


def _generate_wrapper(name: str, cls: type, base_alias: str) -> str:
    """生成单个包装类。"""
    fields = _collect_fields(cls)
    positional = _find_positional(cls)
    seen: set[str] = set()
    param_lines: list[str] = []
    all_names: list[str] = []

    for param_name in positional:
        seen.add(param_name)
        all_names.append(param_name)
        if param_name in fields:
            param_lines.append(
                _make_param(param_name, fields[param_name]).replace("    ", "        ", 1)
            )
        else:
            param_lines.append(f"        {param_name}: Any | None = None,")

    keyword_fields = [(n, fi) for n, fi in fields.items() if n not in seen]
    if keyword_fields:
        if positional:
            param_lines.append("        *,")
        for field_name, field_info in keyword_fields:
            all_names.append(field_name)
            param_lines.append(_make_param(field_name, field_info).replace("    ", "        ", 1))

    param_lines.append("        **kwargs: Any,")

    # 构造 _init_args: 把所有显式参数打包，加上 **kwargs，传给 super()
    pack_lines = ["        _init_args = {"]
    for n in all_names:
        pack_lines.append(f'            "{n}": {n},')
    pack_lines.append("            **kwargs,")
    pack_lines.append("        }")

    params_str = "\n".join(param_lines)
    pack_str = "\n".join(pack_lines)
    return (
        f"# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode\n"
        f"class {name}({base_alias}, _CtxMixin):\n"
        f"    def __init__(\n"
        f"        self,\n"
        f"{params_str}\n"
        f"    ) -> None:\n"
        f"{pack_str}\n"
        f"        super().__init__(**_init_args)"
    )


def generate_prefab_compat() -> str:
    """通过运行时 introspect 生成 prefab_compat.py 内容。"""
    from prefab_ui.components import (
        H1,
        H2,
        Alert,
        AlertDescription,
        AlertTitle,
        Badge,
        Button,
        Card,
        CardContent,
        CardHeader,
        CardTitle,
        Column,
        Container,
        Dashboard,
        DashboardItem,
        DataTable,
        DataTableColumn,
        Dialog,
        Div,
        Form,
        If,
        Input,
        Label,
        Loader,
        Muted,
        Popover,
        Row,
        Select,
        SelectOption,
        Text,
    )

    components = [
        ("Button", Button),
        ("Badge", Badge),
        ("Input", Input),
        ("Select", Select),
        ("SelectOption", SelectOption),
        ("Dashboard", Dashboard),
        ("DashboardItem", DashboardItem),
        ("DataTable", DataTable),
        ("DataTableColumn", DataTableColumn),
        ("Card", Card),
        ("CardHeader", CardHeader),
        ("CardContent", CardContent),
        ("CardTitle", CardTitle),
        ("Row", Row),
        ("Column", Column),
        ("Container", Container),
        ("Dialog", Dialog),
        ("Form", Form),
        ("Alert", Alert),
        ("AlertTitle", AlertTitle),
        ("AlertDescription", AlertDescription),
        ("Div", Div),
        ("H1", H1),
        ("H2", H2),
        ("Label", Label),
        ("Loader", Loader),
        ("Muted", Muted),
        ("Popover", Popover),
        ("Text", Text),
        ("If", If),
    ]

    import_names = sorted({name for name, _ in components})
    # 全部组件统一字母序；Component/DataTableColumn 无别名（供类型标注直接使用），
    # 其余带 _ 前缀别名避免与本地类冲突
    import_names = sorted(set(import_names) | {"Component"})
    aliased_imports = [
        f"    {name}," if name in ("Component", "DataTableColumn") else f"    {name} as _{name},"
        for name in import_names
    ]

    lines = [
        '"""prefab_ui 组件的类型兼容层（自动生成）。',
        "",
        "通过继承为 prefab_ui 组件提供明确的 __init__ 签名和上下文管理器协议，",
        "使 PyCharm 能正确识别参数和 with 语句用法。",
        "",
        "运行时行为与原始组件完全一致，仅影响类型检查。",
        "由 scripts/refresh_prefab_stub.py 自动生成，请勿手动编辑。",
        '"""',
        "",
        "# isort: skip_file  # 生成文件，导入顺序以生成器 + ruff 为准",
        "",
        "",
        "from typing import Any, Literal",
        "",
        "from prefab_ui.actions import Action",
        "from prefab_ui.rx import Rx",
        "from prefab_ui.components import (",
        *aliased_imports,
        ")",
        "",
        "",
        "class _CtxMixin:",
        '    """为组件添加上下文管理器协议类型信息。"""',
        "",
        "    def __enter__(self):",
        "        return self",
        "",
        "    def __exit__(self, *args: Any) -> None:",
        "        pass",
        "",
        "",
    ]

    for name, cls in components:
        if name in _TYPE_ONLY:
            continue
        base_alias = f"_{name}"
        wrapper = _generate_wrapper(name, cls, base_alias)
        lines += [wrapper, "", ""]

    return "\n".join(lines)


# ── 入口 ────────────────────────────────────────────────────────────────────


def main() -> None:
    if not _check_version_changed():
        print(f"prefab_ui v{_get_package_version()} — prefab_compat.py 已是最新，跳过。")
        return

    print(f"Generating prefab_compat.py for prefab_ui v{_get_package_version()}...")

    content = generate_prefab_compat()
    COMPAT_FILE.write_text(content, encoding="utf-8")
    print(f"  [OK] {COMPAT_FILE.relative_to(PROJECT_ROOT)}")

    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", str(COMPAT_FILE)],
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", str(COMPAT_FILE)],
        capture_output=True,
    )
    print("Done.")


if __name__ == "__main__":
    main()
