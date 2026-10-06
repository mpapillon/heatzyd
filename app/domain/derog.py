from enum import IntEnum

from app.domain.modes import Mode


class DerogMode(IntEnum):
    NONE = 0
    VACATIONS = 1
    BOOST = 2
    PRESENCE = 3

    @property
    def mode(self) -> Mode | None:
        match self:
            case DerogMode.BOOST:
                return Mode.CONFORT
            case DerogMode.VACATIONS:
                return Mode.HORS_GEL
            case _:
                return None
