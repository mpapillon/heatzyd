import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app.domain.modes import Mode

TEMPLATES_DIR = Path("app/templates")
SPRITE_PATH = Path("app/static/icons.svg")

_SYMBOL_ID_RE = re.compile(r'<symbol[^>]*\bid="([^"]+)"')

_MODE_ICONS: dict[Mode, str] = {
    Mode.CONFORT: "confort",
    Mode.CONFORT_M1: "confort-1",
    Mode.CONFORT_M2: "confort-2",
    Mode.ECO: "moon",
    Mode.HORS_GEL: "frost",
    Mode.OFF: "power",
    Mode.OFFLINE: "wifi-off",
}

_MODE_LABELS: dict[Mode, str] = {
    Mode.CONFORT: "Confort",
    Mode.CONFORT_M1: "Confort -1°C",
    Mode.CONFORT_M2: "Confort -2°C",
    Mode.ECO: "Éco",
    Mode.HORS_GEL: "Hors-gel",
    Mode.OFF: "Éteint",
    Mode.OFFLINE: "Déconnecté",
}


class UnknownIconError(ValueError):
    pass


@lru_cache(maxsize=1)
def _sprite_source() -> str:
    return SPRITE_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def icon_names() -> frozenset[str]:
    return frozenset(_SYMBOL_ID_RE.findall(_sprite_source()))


def sprite() -> Markup:
    return Markup(_sprite_source())


def icon(
    name: str,
    cls: str = "",
    title: str = "",
    **attrs: object,
) -> Markup:
    known = icon_names()
    if name not in known:
        raise UnknownIconError(
            f"unknown icon {name!r}; available: {', '.join(sorted(known))}"
        )

    classes = " ".join(filter(None, ("icon", cls)))
    extra = "".join(
        f' {key.replace("_", "-")}="{escape(value)}"' for key, value in attrs.items()
    )

    if title:
        a11y = f'role="img" aria-label="{escape(title)}"'
        inner = f"<title>{escape(title)}</title>"
    else:
        a11y = 'aria-hidden="true" focusable="false"'
        inner = ""

    return Markup(
        f'<svg class="{escape(classes)}" '
        f'{a11y}{extra}>{inner}<use href="#{escape(name)}"/></svg>'
    )


def mode_icon_name(mode: Mode | None) -> str:
    if mode is None:
        return "thermometer"
    return _MODE_ICONS[mode]


def mode_value(mode: Mode | None) -> str:
    return mode.value if mode else ""


def mode_label(mode: Mode | None) -> str:
    if mode is None:
        return "Inconnu"
    return _MODE_LABELS.get(mode, "Inconnu")


def mode_icon(
    mode: Mode | None,
    cls: str = "",
) -> Markup:
    name = mode_icon_name(mode)
    return icon(name, cls=cls, title=mode_label(mode))


def short_date(value: str) -> str:
    return date.fromisoformat(value).strftime("%d/%m")


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals.update(
    sprite=sprite,
    icon=icon,
    icon_names=icon_names,
    mode_icon=mode_icon,
    mode_icon_name=mode_icon_name,
    mode_label=mode_label,
    mode_value=mode_value,
    short_date=short_date,
)
