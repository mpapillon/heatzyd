from enum import Enum


class Mode(str, Enum):
    CONFORT = "cft"
    CONFORT_M1 = "cft1"
    CONFORT_M2 = "cft2"
    ECO = "eco"
    HORS_GEL = "fro"
    OFF = "stop"

    # Non-standard modes
    OFFLINE = "offline"
