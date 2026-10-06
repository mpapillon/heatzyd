import pytest

from app.templating import short_date


def test_short_date_drops_the_year() -> None:
    assert short_date("2026-10-08") == "08/10"


def test_short_date_pads_single_digits() -> None:
    assert short_date("2026-01-05") == "05/01"


def test_short_date_rejects_a_non_date() -> None:
    with pytest.raises(ValueError):
        short_date("not-a-date")
