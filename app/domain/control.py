def backoff(attempts: int, base: float, cap: float) -> float:
    return min(base * 2 ** (attempts - 1), cap)
