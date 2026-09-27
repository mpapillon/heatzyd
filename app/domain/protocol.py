import logging
from typing import Any

from app.domain.capabilities import ProductCapabilities
from app.domain.errors import ModeNotSupported
from app.domain.modes import Mode

logger = logging.getLogger(__name__)


def parse_mode(raw: str | None) -> Mode | None:
    if raw is None:
        return None
    try:
        return Mode(raw)
    except ValueError:
        logger.warning("unknown mode: %r", raw)
        return None


def parse_bool(raw: object) -> bool:
    return raw == 1


def extract_mode(attrs: dict[str, Any]) -> Mode | None:
    return parse_mode(attrs.get("mode"))


def encode_order(cap: ProductCapabilities, mode: Mode) -> dict[str, Any]:
    if not cap.supports(mode):
        raise ModeNotSupported(mode.value)
    return {"attrs": {"mode": mode.value}}
