"""权限发现（`auth/discovery.py`）的自洽守卫。

`get_all_permissions` 只扫 `_TOOL_MODULES` 里列出的模块，而那份清单是手写的。新工具模块漏登记
时症状很轻：工具照旧能用、超管照旧能调（装饰器对超管直接放行），但那枚权限码永远不进
`/permissions` —— 后端 RBAC 只灌那一枚清单，于是清单外的码没人能被授予，除超管以外一律 403，
而现场看起来只是"这个按钮对别人不亮"。本文件把"声明过码的模块必须都在清单里"钉成可红的断言。
"""

import importlib
import inspect
import pkgutil

import service_mcp.tools as tools_pkg
from service_mcp.auth import discovery


def _declared_perm_codes() -> dict[str, set[str]]:
    """逐个 import 工具包里的模块，收集它们声明的权限码（模块级带 `_mcp_perm_code` 的函数）。

    判据取"这个模块声明过码"而不是"这个模块叫 ××_tools"：工厂模块（crud_factory）在运行时
    才造出带码的函数、自己不声明任何码，按码存在性过滤正好把它排除。
    """
    declared: dict[str, set[str]] = {}
    for info in pkgutil.iter_modules(tools_pkg.__path__):
        mod = importlib.import_module(f"{tools_pkg.__name__}.{info.name}")
        codes = {
            obj._mcp_perm_code
            for obj in vars(mod).values()
            if inspect.isfunction(obj) and hasattr(obj, "_mcp_perm_code")
        }
        if codes:
            declared[mod.__name__] = codes
    return declared


def test_every_module_declaring_perm_codes_is_registered():
    """工具包里声明了权限码的模块，必须都登记进 `_TOOL_MODULES`。"""
    registered = {mod.__name__ for mod in discovery._TOOL_MODULES}
    missing = sorted(set(_declared_perm_codes()) - registered)

    assert not missing, f"这些工具模块未登记进 _TOOL_MODULES，其权限码进不了 /permissions：{missing}"


def test_every_declared_perm_code_is_discoverable():
    """上一条件的后果版：任何声明过的码都要出现在下发清单里（清单是被 RBAC 消费的那一枚）。"""
    discovered = {p["code"] for p in discovery.get_all_permissions()}

    for mod_name, codes in sorted(_declared_perm_codes().items()):
        assert codes <= discovered, f"{mod_name} 声明的 {sorted(codes - discovered)} 没进权限清单"


def test_discovered_permission_names_are_resolvable():
    """每枚下发的码都要能查到资源名与操作名。

    资源码/操作码在 `AuthResource`/`AuthAction` 里查不到时不会报错：`_make_name` 经
    `getattr(None, "label", …)` 兜底，清单里那枚名字静默变成"××未定义"，后端原样写进 RBAC 表。
    """
    for perm in discovery.get_all_permissions():
        name = perm["name"]
        hint = (
            f"{perm['code']} 的名字兜底了：{name}（资源 {perm['resource']!r} / 操作 {perm['action']!r} "
            "需在 AuthResource/AuthAction 里补成员）"
        )
        assert "未定义" not in name, hint
        assert "未知" not in name, hint
