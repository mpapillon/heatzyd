from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.derog import days_until

PARIS = ZoneInfo("Europe/Paris")


def test_tomorrow_from_the_evening_is_one_day() -> None:
    # le défaut de l'UI (« le lendemain ») : 12 h de délai, pas 0 jour
    now = datetime(2026, 8, 1, 21, 0)
    assert days_until(datetime(2026, 8, 2, 9, 0), now=now) == 1


def test_exactly_one_day() -> None:
    now = datetime(2026, 8, 1, 9, 0)
    assert days_until(datetime(2026, 8, 2, 9, 0), now=now) == 1


def test_rounds_up_to_cover_the_return_date() -> None:
    # ceil : 13 jours et demi -> 14 jours, jamais d'expiration avant la date
    now = datetime(2026, 8, 1, 21, 0)
    assert days_until(datetime(2026, 8, 15, 0, 0), now=now) == 14


def test_same_instant_is_rejected() -> None:
    now = datetime(2026, 8, 1, 12, 0)
    with pytest.raises(ValueError, match="future"):
        days_until(now, now=now)


def test_past_date_is_rejected() -> None:
    now = datetime(2026, 8, 5, 12, 0)
    with pytest.raises(ValueError, match="future"):
        days_until(datetime(2026, 8, 1, 12, 0), now=now)


def test_255_days_is_the_upper_bound() -> None:
    now = datetime(2026, 8, 1, 12, 0)
    assert days_until(now + timedelta(days=255), now=now) == 255


def test_more_than_255_days_is_rejected() -> None:
    now = datetime(2026, 8, 1, 12, 0)
    with pytest.raises(ValueError, match="255"):
        days_until(now + timedelta(days=256), now=now)


def test_no_timezone_does_not_raise() -> None:
    # HEATZYD_TZ non défini (cas par défaut) : les deux côtés passent par
    # astimezone(None), donc aware/aware — pas de TypeError naive/aware
    now = datetime(2026, 8, 1, 9, 0)
    assert days_until(datetime(2026, 8, 3, 9, 0), now=now, tz=None) == 2


def test_naive_datetimes_under_a_timezone() -> None:
    # les deux côtés naïfs sont ramenés dans le même fuseau : le delta est
    # indépendant du fuseau système
    now = datetime(2026, 8, 1, 9, 0)
    assert days_until(datetime(2026, 8, 3, 9, 0), now=now, tz=PARIS) == 2


def test_aware_datetimes_under_a_timezone() -> None:
    now = datetime(2026, 8, 1, 9, 0, tzinfo=PARIS)
    ends = datetime(2026, 8, 3, 9, 0, tzinfo=PARIS)
    assert days_until(ends, now=now, tz=PARIS) == 2


def test_naive_form_date_is_read_in_the_app_timezone() -> None:
    # now est conscient (fuseau de l'app) ; ends_at vient d'un formulaire (naif)
    # et doit etre lu comme une heure de Paris, pas comme une heure systeme :
    # les deux sont a 26 h d'ecart -> 2 jours
    now = datetime(2026, 8, 1, 23, 0, tzinfo=PARIS)
    ends = datetime(2026, 8, 3, 1, 0)
    assert days_until(ends, now=now, tz=PARIS) == 2


def test_counts_absolute_time_across_a_dst_change() -> None:
    # Europe/Paris : la nuit du 25 octobre 2026, les heures reculent d'une
    # heure — les deux dates locales sont à 49 h d'écart réel, donc 3 jours
    # (une soustraction naïve donnerait 48 h, soit 2 jours).
    now = datetime(2026, 10, 24, 12, 0, tzinfo=PARIS)
    ends = datetime(2026, 10, 26, 12, 0, tzinfo=PARIS)
    assert days_until(ends, now=now, tz=PARIS) == 3
