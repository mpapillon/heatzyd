import logging
from typing import Any

from app.domain.capabilities import ProductCapabilities
from app.domain.derog import DerogMode
from app.domain.errors import DerogNotSupported, LockNotSupported, ModeNotSupported
from app.domain.modes import Mode

logger = logging.getLogger(__name__)

ALIAS_MAX_LENGTH = 16


def parse_mode(raw: str | None) -> Mode | None:
    if raw is None:
        return None
    try:
        return Mode(raw)
    except ValueError:
        logger.warning("unknown mode: %r", raw)
        return None


def parse_derog_mode(raw: object) -> DerogMode:
    if raw is None:
        return DerogMode.NONE
    try:
        return DerogMode(raw)
    except ValueError:
        logger.warning("unknown derog_mode: %r", raw)
        return DerogMode.NONE


def parse_int(raw: object, default: int = 0) -> int:
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            return default
    return default


def parse_int_flag(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true"}
    return False


def parse_remark(remark: str) -> dict[str, str]:
    if not remark:
        return {}
    return dict(pair.split("=", 1) for pair in remark.split("|"))


def extract_mode(attrs: dict[str, Any]) -> Mode | None:
    return parse_mode(attrs.get("mode"))


def extract_derog_mode(attrs: dict[str, Any]) -> DerogMode:
    return parse_derog_mode(attrs.get("derog_mode"))


def encode_order(cap: ProductCapabilities, mode: Mode) -> dict[str, Any]:
    if not cap.supports_mode(mode):
        raise ModeNotSupported(mode.value)
    return {"attrs": {"mode": mode.value}}


def encode_lock(cap: ProductCapabilities, lock: bool) -> dict[str, Any]:
    if not cap.lock:
        raise LockNotSupported
    return {"attrs": {"lock_switch": 1 if lock else 0}}


def encode_derog(
    cap: ProductCapabilities, kind: DerogMode, time: int = 0
) -> dict[str, Any]:
    if not cap.supports_derog(kind):
        raise DerogNotSupported
    if kind == DerogMode.NONE:
        if time != 0:
            raise ValueError("time must be 0 for NONE derog")
    elif not 1 <= time <= 255:
        raise ValueError("time must be between 1 and 255")

    attrs: dict[str, Any] = {
        "derog_mode": kind.value,
        "derog_time": time,
    }
    if kind.mode is not None:
        attrs["mode"] = kind.mode.value
    return {"attrs": attrs}
