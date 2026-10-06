import pytest

from app.domain.capabilities import (
    CAPS_PILOTE_GEN_1,
    CAPS_PILOTE_GEN_4,
    ProductCapabilities,
)
from app.domain.derog import DerogMode
from app.domain.errors import DerogNotSupported
from app.domain.modes import Mode
from app.domain.protocol import (
    encode_derog,
    extract_derog_mode,
    parse_derog_mode,
    parse_int,
    parse_remark,
)


def _caps(boost: bool = True, vacations: bool = True) -> ProductCapabilities:
    return ProductCapabilities(modes=(Mode.ECO,), boost=boost, vacations=vacations)


# parse / extract


def test_parse_derog_mode_valid() -> None:
    assert parse_derog_mode(2) is DerogMode.BOOST


def test_parse_derog_mode_missing_is_none() -> None:
    assert parse_derog_mode(None) is DerogMode.NONE


def test_parse_derog_mode_unknown_falls_back_to_none() -> None:
    assert parse_derog_mode(99) is DerogMode.NONE


def test_extract_derog_mode() -> None:
    assert extract_derog_mode({"derog_mode": 1}) is DerogMode.VACATIONS
    assert extract_derog_mode({}) is DerogMode.NONE


def test_parse_int() -> None:
    assert parse_int("42") == 42
    assert parse_int(" 7 ") == 7
    assert parse_int(3) == 3
    assert parse_int(3.9) == 3
    assert parse_int(None) == 0
    assert parse_int(True) == 0
    assert parse_int("nope", default=-1) == -1


def test_parse_remark_splits_pairs() -> None:
    remark = "range=4|isdelete=1|gid=0|groupname=|grouprange=4"

    assert parse_remark(remark) == {
        "range": "4",
        "isdelete": "1",
        "gid": "0",
        "groupname": "",
        "grouprange": "4",
    }


def test_parse_remark_keeps_equals_in_value() -> None:
    assert parse_remark("range=4|groupname=a=b") == {
        "range": "4",
        "groupname": "a=b",
    }


# supports_derog


def test_supports_derog_gen_4() -> None:
    assert CAPS_PILOTE_GEN_4.supports_derog(DerogMode.BOOST) is True
    assert CAPS_PILOTE_GEN_4.supports_derog(DerogMode.VACATIONS) is True
    assert CAPS_PILOTE_GEN_4.supports_derog(DerogMode.NONE) is True
    assert CAPS_PILOTE_GEN_4.supports_derog(DerogMode.PRESENCE) is False


def test_supports_derog_gen_1_has_none() -> None:
    assert CAPS_PILOTE_GEN_1.supports_derog(DerogMode.BOOST) is False
    assert CAPS_PILOTE_GEN_1.supports_derog(DerogMode.VACATIONS) is False
    assert CAPS_PILOTE_GEN_1.supports_derog(DerogMode.NONE) is False


def test_supports_derog_none_requires_at_least_one_kind() -> None:
    assert _caps(boost=False, vacations=False).supports_derog(DerogMode.NONE) is False
    assert _caps(boost=True, vacations=False).supports_derog(DerogMode.NONE) is True


# encode_derog


def test_encode_derog_none_clears_payload() -> None:
    assert encode_derog(CAPS_PILOTE_GEN_4, DerogMode.NONE) == {
        "attrs": {"derog_mode": 0, "derog_time": 0}
    }


def test_encode_derog_boost_is_minutes() -> None:
    assert encode_derog(CAPS_PILOTE_GEN_4, DerogMode.BOOST, 90) == {
        "attrs": {"derog_mode": 2, "derog_time": 90, "mode": "cft"}
    }


def test_encode_derog_vacations_is_days() -> None:
    assert encode_derog(CAPS_PILOTE_GEN_4, DerogMode.VACATIONS, 5) == {
        "attrs": {"derog_mode": 1, "derog_time": 5, "mode": "fro"}
    }


def test_encode_derog_unsupported_product() -> None:
    with pytest.raises(DerogNotSupported):
        encode_derog(CAPS_PILOTE_GEN_1, DerogMode.BOOST, 30)


def test_encode_derog_presence_not_pilotable() -> None:
    with pytest.raises(DerogNotSupported):
        encode_derog(CAPS_PILOTE_GEN_4, DerogMode.PRESENCE, 1)


def test_encode_derog_boost_disabled_for_product() -> None:
    with pytest.raises(DerogNotSupported):
        encode_derog(_caps(boost=False), DerogMode.BOOST, 30)


@pytest.mark.parametrize("time", [0, -1, 256])
def test_encode_derog_time_out_of_range(time: int) -> None:
    with pytest.raises(ValueError):
        encode_derog(CAPS_PILOTE_GEN_4, DerogMode.BOOST, time)


def test_encode_derog_none_with_time_is_rejected() -> None:
    with pytest.raises(ValueError):
        encode_derog(CAPS_PILOTE_GEN_4, DerogMode.NONE, 5)
