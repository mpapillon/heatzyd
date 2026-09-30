from app.domain.control import backoff


def test_backoff_is_exponential_until_cap() -> None:
    assert [backoff(n, 15, 240) for n in range(1, 6)] == [15, 30, 60, 120, 240]


def test_backoff_first_attempt_is_base() -> None:
    assert backoff(1, 15, 240) == 15


def test_backoff_is_capped() -> None:
    assert backoff(10, 15, 240) == 240
