from concurrent.futures import ThreadPoolExecutor

from django_ratelatch.backends.memory import MemoryBackend
from django_ratelatch.core.algorithms.fixed_window import FixedWindow


def test_concurrent_requests_do_not_exceed_limit(monkeypatch):
    monkeypatch.setattr(
        "django_ratelatch.core.algorithms.fixed_window.time",
        lambda: 1000,
    )

    backend = MemoryBackend()
    limit = 10
    limiter = FixedWindow(limit=limit, window_size=60, backend=backend)

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(
            executor.map(
                lambda _: limiter.check("client-1"),
                range(100),
            )
        )

    allowed_count = sum(decision["allowed"] for decision in decisions)
    assert allowed_count == limit

    state = backend.get("fixed_window:client-1")
    assert state is not None
    assert state["request_count"] == limit