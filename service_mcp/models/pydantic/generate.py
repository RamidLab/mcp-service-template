import os
from pathlib import Path
from typing import Any


_pyi_registry: dict[Path, dict[str, dict[str, Any]]] = {}


def register_pyi_class(
    class_name: str,
    base_class: type,
    pyi_file: str,
    cls: type | None = None,
    explicit: bool = False,
) -> None:
    """注册一个动态生成的类到 .pyi stub 生成队列。

    Args:
        class_name: 类名
        base_class: 基类
        pyi_file: 目标 .pyi 文件名（不含扩展名）
        cls: 动态生成的类（用于提取字段定义）
        explicit: 该名称在声明文件中是显式 class（继承动态基类），
                  需要生成完整 class stub（含 to_where 签名）；
                  动态变量赋值（如 ``X = create_filter_class(...)``）保持 False
    """
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    target_pyi = Path(os.path.join(curr_dir, pyi_file)).with_suffix(".pyi").resolve()
    base_qual = f"{base_class.__module__}.{base_class.__qualname__}"

    fields: dict[str, str] = {}
    if cls is not None and hasattr(cls, "model_fields"):
        for f_name, f_info in cls.model_fields.items():
            annotation = f_info.annotation
            if annotation is None:
                continue
            # 动态类字段支持 FilterField 对象或裸值（等值兼容），stub 放宽为 Any 避免误报
            default = " = None" if not f_info.is_required() else ""
            fields[f_name] = f"Any{default}"

    registry = _pyi_registry.setdefault(target_pyi, {})
    registry[class_name] = {
        "base_qual": base_qual,
        "base_name": base_class.__name__,
        "fields": fields,
        "explicit": explicit,
    }
    _write_pyi(target_pyi)


def _type_to_str(tp: Any) -> str:
    """将类型注解转为字符串表示"""
    origin = getattr(tp, "__origin__", None)

    # Optional[X] → X | None
    from typing import Literal, Union

    if origin is Union:
        args = [a for a in tp.__args__ if a is not type(None)]
        has_none = type(None) in tp.__args__
        if len(args) == 1:
            inner = _type_to_str(args[0])
            return f"{inner} | None" if has_none else inner
        inner = ", ".join(_type_to_str(a) for a in args)
        return f"Union[{inner}]" + (" | None" if has_none else "")

    # Literal["a", "b"]
    if origin is Literal:
        vals = ", ".join(f'"{v}"' if isinstance(v, str) else repr(v) for v in tp.__args__)
        return f"Literal[{vals}]"

    # list[X], dict[K, V], etc.
    if origin is not None:
        type_args: tuple[Any, ...] = getattr(tp, "__args__", ()) or ()
        origin_name: str = (
            getattr(origin, "__name__", "") or getattr(origin, "__qualname__", "") or "Any"
        )
        if type_args:
            inner = ", ".join(_type_to_str(a) for a in type_args)
            return f"{origin_name}[{inner}]"
        return origin_name

    # 普通类型
    if hasattr(tp, "__name__"):
        return tp.__name__
    return str(tp)


def _write_pyi(pyi_path: Path) -> None:
    """生成 .pyi stub：变量声明形式（与实现的 ``X = create_filter_class(...)`` 赋值一致）。

    动态类无法静态声明字段（PyCharm 对 stub class 与变量赋值合并会报类型不匹配），
    字段参数提示由工具层运行时注解注入（见 crud_factory._annotate）承担。

    显式 class 声明的过滤器（注册时 explicit=True，如 ProductFilter）需补充完整 class stub
    以满足 PyCharm 的抽象方法检查。
    """
    registry = _pyi_registry.get(pyi_path, {})
    if not registry:
        return

    imports: dict[str, set[str]] = {}
    for reg_entry in registry.values():
        parts = reg_entry["base_qual"].rsplit(".", 1)
        if len(parts) == 2:
            mod, cls = parts
            imports.setdefault(mod, set()).add(cls)
    # 显式 class stub（如 ProductFilter）用到 ColumnElement（to_where 返回类型）和 Any（字段类型），
    # 仅当目标 stub 含显式 class 时添加，避免 search.pyi 出现未使用导入
    if any(e.get("explicit") for e in registry.values()):
        imports.setdefault("sqlalchemy", set()).add("ColumnElement")
        imports.setdefault("typing", set()).add("Any")

    lines = []
    if imports:
        # isort 分组：第三方包在前（字母序），第一方 service_mcp.* 最后
        first_party = sorted(m for m in imports if m.startswith("service_mcp"))
        third_party = sorted(m for m in imports if not m.startswith("service_mcp"))
        for mod in third_party + first_party:
            lines.append(f"from {mod} import {', '.join(sorted(imports[mod]))}")
    lines.append("")

    for cls_name in sorted(registry.keys()):
        entry: dict[str, Any] = registry[cls_name]
        base_short = entry["base_qual"].rsplit(".", 1)[-1]
        if entry.get("explicit"):
            # 显式 class：_filter_mappings/_model_class 继承基类默认实现（非抽象），
            # 只声明该 class 特有的 to_where 与字段
            # class 前加空行（ruff format 要求变量声明与 class 定义之间空一行）
            lines.append("")
            lines.append(f"class {cls_name}({base_short}):")
            lines.append("    def to_where(self) -> list[ColumnElement[bool]]: ...")
            fields: dict[str, str] = entry["fields"]
            for f_name in sorted(fields):
                lines.append(f"    {f_name}: {fields[f_name]}")
            lines.append("")
        else:
            lines.append(f"{cls_name}: type[{base_short}]")
    lines.append("")

    pyi_path.write_text("\n".join(lines), encoding="utf-8")


def clean_registry() -> None:
    _pyi_registry.clear()
