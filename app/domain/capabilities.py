from dataclasses import dataclass

from app.domain.modes import NON_COMMANDABLE_MODES, Mode


@dataclass(frozen=True, slots=True)
class ProductCapabilities:
    modes: tuple[Mode, ...]
    lock: bool = True
    boost: bool = True
    program: bool = True
    vacations: bool = True

    def supports(self, mode: Mode) -> bool:
        return mode not in NON_COMMANDABLE_MODES and mode in self.modes


_MODES_BASE = (Mode.CONFORT, Mode.ECO, Mode.HORS_GEL, Mode.OFF)
_MODES_GEN_4 = tuple(m for m in Mode if m not in NON_COMMANDABLE_MODES)

CAPS_PILOTE_GEN_1 = ProductCapabilities(
    modes=_MODES_BASE, lock=False, boost=False, vacations=False
)
CAPS_PILOTE_GEN_2 = ProductCapabilities(modes=_MODES_BASE)
CAPS_PILOTE_GEN_3 = CAPS_PILOTE_GEN_2
CAPS_PILOTE_GEN_4 = ProductCapabilities(modes=_MODES_GEN_4)

PILOTE_GEN_1 = (
    "9420ae048da545c88fc6274d204dd25f",  # Heatzy
)

PILOTE_GEN_2 = (
    "51d16c22a5f74280bc3cfe9ebcdc6402",  # Pilote2
    "4fc968a21e7243b390e9ede6f1c6465d",  # Elec_Pro
)

PILOTE_GEN_3 = (
    "b9a67b6ce24b437d9794103fd317e627",  # Pilote_Soc
    "b8c6657b66c34148b4dee64d615cefc7",  # Elec_Pro_Soc
)

PILOTE_GEN_4 = (
    "46409c7f29d4411c85a3a46e5ee3703e",  # Pilote_Soc_C3
    "9dacde7ef459421eaf8dc4bea9385634",  # Elec_Pro_Ble
)

CAPABILITIES: dict[str, ProductCapabilities] = {
    **{k: CAPS_PILOTE_GEN_1 for k in PILOTE_GEN_1},
    **{k: CAPS_PILOTE_GEN_2 for k in PILOTE_GEN_2},
    **{k: CAPS_PILOTE_GEN_3 for k in PILOTE_GEN_3},
    **{k: CAPS_PILOTE_GEN_4 for k in PILOTE_GEN_4},
}


def capabilities_for(product_key: str) -> ProductCapabilities | None:
    """ProductCapabilities, or ``None`` if product is unknown (not supported)."""
    return CAPABILITIES.get(product_key)
