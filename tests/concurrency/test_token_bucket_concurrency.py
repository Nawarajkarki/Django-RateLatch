from concurrent.futures import ThreadPoolExecutor

from django_ratelatch.backends.memory import MemoryBackend
from django_ratelatch.core.algorithms.token_bucket import TokenBucket


def test_concurrent_requests_do_not_exceed_burst_capacity(monkeypatch):
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.token_bucket.time",
        lambda: 1000,
    )

    backend = MemoryBackend()
    burst_capacity = 10
    limiter = TokenBucket(
        limit=5,
        window_size=60,
        burst_capacity=burst_capacity,
        backend=backend,
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(
            executor.map(
                lambda _: limiter.check("client-1"),
                range(100),
            )
        )

    assert sum(decision["allowed"] for decision in decisions) == burst_capacity

    state = backend.get("token_bucket:client-1")
    assert state is not None
    assert state["tokens"] == 0