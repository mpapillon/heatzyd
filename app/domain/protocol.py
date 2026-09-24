import logging

from app.domain.modes import Mode

logger = logging.getLogger(__name__)


def parse_mode(raw: str | None) -> Mode | None:
    if raw is None:
        return None
    try:
        return Mode(raw)
    except ValueError:
        logger.warning("unkown mode: %r", raw)
        return None


def parse_bool(raw: object) -> bool:
    return raw == 1
