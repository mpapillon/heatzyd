from app.domain.capabilities import CAPABILITIES
from app.domain.derog import DerogMode


def test_every_derog_cap_supports_the_mode_that_will_be_sent() -> None:
    for product_key, cap in CAPABILITIES.items():
        for kind in DerogMode:
            if kind.mode is None:
                continue
            if cap.supports_derog(kind):
                assert kind.mode in cap.modes, (
                    f"{product_key}: {kind.name} envoye {kind.mode.value} "
                    f"que le profil ne supporte pas"
                )
