"""prefab_ui 组件的类型兼容层（自动生成）。

通过继承为 prefab_ui 组件提供明确的 __init__ 签名和上下文管理器协议，
使 PyCharm 能正确识别参数和 with 语句用法。

运行时行为与原始组件完全一致，仅影响类型检查。
由 scripts/refresh_prefab_stub.py 自动生成，请勿手动编辑。
"""

# isort: skip_file  # 生成文件，导入顺序以生成器 + ruff 为准

from typing import Any

from prefab_ui.actions import Action
from prefab_ui.components import (
    H1 as _H1,
)
from prefab_ui.components import (
    H2 as _H2,
)
from prefab_ui.components import (
    Alert as _Alert,
)
from prefab_ui.components import (
    AlertDescription as _AlertDescription,
)
from prefab_ui.components import (
    AlertTitle as _AlertTitle,
)
from prefab_ui.components import (
    Badge as _Badge,
)
from prefab_ui.components import (
    Button as _Button,
)
from prefab_ui.components import (
    Card as _Card,
)
from prefab_ui.components import (
    CardContent as _CardContent,
)
from prefab_ui.components import (
    CardHeader as _CardHeader,
)
from prefab_ui.components import (
    CardTitle as _CardTitle,
)
from prefab_ui.components import (
    Column as _Column,
)
from prefab_ui.components import (
    Component,
    DataTableColumn,
)
from prefab_ui.components import (
    Container as _Container,
)
from prefab_ui.components import (
    Dashboard as _Dashboard,
)
from prefab_ui.components import (
    DashboardItem as _DashboardItem,
)
from prefab_ui.components import (
    DataTable as _DataTable,
)
from prefab_ui.components import (
    Dialog as _Dialog,
)
from prefab_ui.components import (
    Div as _Div,
)
from prefab_ui.components import (
    Form as _Form,
)
from prefab_ui.components import (
    If as _If,
)
from prefab_ui.components import (
    Input as _Input,
)
from prefab_ui.components import (
    Label as _Label,
)
from prefab_ui.components import (
    Loader as _Loader,
)
from prefab_ui.components import (
    Muted as _Muted,
)
from prefab_ui.components import (
    Popover as _Popover,
)
from prefab_ui.components import (
    Row as _Row,
)
from prefab_ui.components import (
    Select as _Select,
)
from prefab_ui.components import (
    SelectOption as _SelectOption,
)
from prefab_ui.components import (
    Text as _Text,
)
from prefab_ui.rx import Rx


class _CtxMixin:
    """为组件添加上下文管理器协议类型信息。"""

    def __enter__(self):
        return self

    def __exit__(self, *args: Any) -> None:
        pass


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Button(_Button, _CtxMixin):
    def __init__(
        self,
        label: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        icon: str | None = None,
        variant: str | Rx = "default",
        size: str = "default",
        button_type: str | None = None,
        disabled: bool | str | Rx = False,
        on_click: Action | list[Action] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "label": label,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "icon": icon,
            "variant": variant,
            "size": size,
            "button_type": button_type,
            "disabled": disabled,
            "on_click": on_click,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Badge(_Badge, _CtxMixin):
    def __init__(
        self,
        label: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        variant: str | Rx = "default",
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "label": label,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "variant": variant,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Input(_Input, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        name: str | None = None,
        value: str | Rx | None = None,
        input_type: str = "text",
        placeholder: str | Rx | None = None,
        disabled: bool = False,
        read_only: bool = False,
        required: bool = False,
        min_length: int | None = None,
        max_length: int | None = None,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        pattern: str | None = None,
        on_change: Action | list[Action] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "name": name,
            "value": value,
            "input_type": input_type,
            "placeholder": placeholder,
            "disabled": disabled,
            "read_only": read_only,
            "required": required,
            "min_length": min_length,
            "max_length": max_length,
            "min": min,
            "max": max,
            "step": step,
            "pattern": pattern,
            "on_change": on_change,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Select(_Select, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        name: str | None = None,
        value: str | None = None,
        placeholder: str | Rx | None = None,
        size: str = "default",
        side: str | None = None,
        align: str | None = None,
        disabled: bool = False,
        required: bool = False,
        invalid: bool = False,
        on_change: Action | list[Action] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "name": name,
            "value": value,
            "placeholder": placeholder,
            "size": size,
            "side": side,
            "align": align,
            "disabled": disabled,
            "required": required,
            "invalid": invalid,
            "on_change": on_change,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class SelectOption(_SelectOption, _CtxMixin):
    def __init__(
        self,
        label: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        value: str | Rx | None = None,
        selected: bool = False,
        disabled: bool = False,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "label": label,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "value": value,
            "selected": selected,
            "disabled": disabled,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Dashboard(_Dashboard, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        columns: int = 12,
        row_height: int | str = 120,
        rows: int | None = None,
        gap: int | tuple[int | None, int | None] | Any | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "columns": columns,
            "row_height": row_height,
            "rows": rows,
            "gap": gap,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class DashboardItem(_DashboardItem, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        col: int = 1,
        row: int = 1,
        col_span: int = 1,
        row_span: int = 1,
        z_index: int | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "col": col,
            "row": row,
            "col_span": col_span,
            "row_span": row_span,
            "z_index": z_index,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class DataTable(_DataTable, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        columns: list[DataTableColumn] | None = None,
        rows: list[dict[str, Any] | Any] | str | Rx | None = None,
        search: bool = False,
        paginated: bool = False,
        page_size: int = 10,
        on_row_click: Action | list[Action] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "columns": columns,
            "rows": rows,
            "search": search,
            "paginated": paginated,
            "page_size": page_size,
            "on_row_click": on_row_click,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Card(_Card, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class CardHeader(_CardHeader, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class CardContent(_CardContent, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class CardTitle(_CardTitle, _CtxMixin):
    def __init__(
        self,
        content: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "content": content,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Row(_Row, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        gap: int | tuple[int | None, int | None] | Any | None = None,
        align: str | None = None,
        justify: str | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "gap": gap,
            "align": align,
            "justify": justify,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Column(_Column, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        gap: int | tuple[int | None, int | None] | Any | None = None,
        align: str | None = None,
        justify: str | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "gap": gap,
            "align": align,
            "justify": justify,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Container(_Container, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Dialog(_Dialog, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        title: str | Rx | None = None,
        description: str | Rx | None = None,
        name: str | None = None,
        dismissible: bool = True,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "title": title,
            "description": description,
            "name": name,
            "dismissible": dismissible,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Form(_Form, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        gap: int = 4,
        on_submit: Action | list[Action] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "gap": gap,
            "on_submit": on_submit,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Alert(_Alert, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        variant: str | Rx = "default",
        icon: str | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "variant": variant,
            "icon": icon,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class AlertTitle(_AlertTitle, _CtxMixin):
    def __init__(
        self,
        content: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "content": content,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class AlertDescription(_AlertDescription, _CtxMixin):
    def __init__(
        self,
        content: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "content": content,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Div(_Div, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        style: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "style": style,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class H1(_H1, _CtxMixin):
    def __init__(
        self,
        content: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strikethrough: bool | None = None,
        uppercase: bool | None = None,
        lowercase: bool | None = None,
        code: bool | None = None,
        align: str | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "content": content,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "strikethrough": strikethrough,
            "uppercase": uppercase,
            "lowercase": lowercase,
            "code": code,
            "align": align,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class H2(_H2, _CtxMixin):
    def __init__(
        self,
        content: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strikethrough: bool | None = None,
        uppercase: bool | None = None,
        lowercase: bool | None = None,
        code: bool | None = None,
        align: str | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "content": content,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "strikethrough": strikethrough,
            "uppercase": uppercase,
            "lowercase": lowercase,
            "code": code,
            "align": align,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Label(_Label, _CtxMixin):
    def __init__(
        self,
        text: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        for_id: str | None = None,
        optional: bool = False,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "text": text,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "for_id": for_id,
            "optional": optional,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Loader(_Loader, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        variant: str = "spin",
        size: str = "default",
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "variant": variant,
            "size": size,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Muted(_Muted, _CtxMixin):
    def __init__(
        self,
        content: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strikethrough: bool | None = None,
        uppercase: bool | None = None,
        lowercase: bool | None = None,
        code: bool | None = None,
        align: str | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "content": content,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "strikethrough": strikethrough,
            "uppercase": uppercase,
            "lowercase": lowercase,
            "code": code,
            "align": align,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Popover(_Popover, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        title: str | Rx | None = None,
        description: str | Rx | None = None,
        side: str | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            "title": title,
            "description": description,
            "side": side,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class Text(_Text, _CtxMixin):
    def __init__(
        self,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        content: str | Rx | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        underline: bool | None = None,
        strikethrough: bool | None = None,
        uppercase: bool | None = None,
        lowercase: bool | None = None,
        code: bool | None = None,
        align: str | None = None,
        children: list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "content": content,
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "strikethrough": strikethrough,
            "uppercase": uppercase,
            "lowercase": lowercase,
            "code": code,
            "align": align,
            "children": children,
            **kwargs,
        }
        super().__init__(**_init_args)


# noinspection PyShadowingBuiltins,PyMethodMayBeStatic,DuplicatedCode
class If(_If, _CtxMixin):
    def __init__(
        self,
        condition: str | Rx | None = None,
        *,
        id: str | None = None,
        css_class: str | None = None,
        on_mount: Any | None = None,
        children: list[Component] | None = None,
        let: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        _init_args = {
            "condition": condition,
            "id": id,
            "css_class": css_class,
            "on_mount": on_mount,
            "children": children,
            "let": let,
            **kwargs,
        }
        super().__init__(**_init_args)
