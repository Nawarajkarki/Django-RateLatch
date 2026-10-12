from concurrent.futures import ThreadPoolExecutor

from django_ratelimiter.backends.memory import MemoryBackend
from django_ratelimiter.core.algorithms.sliding_window_counter import SlidingWindowCounter


def test_concurrent_requests_do_not_exceed_limit(monkeypatch):
    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.sliding_window_counter.time",
        lambda: 1000,
    )

    backend = MemoryBackend()
    limit = 5
    limiter = SlidingWindowCounter(
        limit=limit,
        window_size=10,
        backend=backend,
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(
            executor.map(
                lambda _: limiter.check("client-1"),
                range(100),
            )
        )

    assert sum(decision["allowed"] for decision in decisions) == limit

    state = backend.get("sliding_window_counter:client-1")
    assert state is not None
    assert state["current_count"] == limit