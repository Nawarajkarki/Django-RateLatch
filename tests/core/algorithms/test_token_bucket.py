import pytest

from django_ratelimiter.backends.memory import MemoryBackend
from django_ratelimiter.core.algorithms.token_bucket import TokenBucket


CLOCK_PATH = "django_ratelimiter.core.algorithms.token_bucket.time"


def set_clock(monkeypatch, timestamp):
    monkeypatch.setattr(CLOCK_PATH, lambda: timestamp)


def test_bucket_starts_full_and_allows_burst_up_to_capacity(monkeypatch):
    set_clock(monkeypatch, 1000)
    backend = MemoryBackend()
    limiter = TokenBucket(
        limit=2,
        window_size=10,
        burst_capacity=2,
        backend=backend,
    )

    assert limiter.check("client-1") == {"allowed": True}
    assert limiter.check("client-1") == {"allowed": True}

    result = limiter.check("client-1")
    assert result == {"allowed": False, "retry_after": 5}


def test_refills_continuously_and_allows_when_token_is_available(monkeypatch):
    set_clock(monkeypatch, 1000)
    backend = MemoryBackend()
    limiter = TokenBucket(
        limit=2,
        window_size=10,
        burst_capacity=2,
        backend=backend,
    )

    limiter.check("client-1")
    limiter.check("client-1")

    set_clock(monkeypatch, 1004)
    state_before_rejection = backend.get("token_bucket:client-1")

    result = limiter.check("client-1")

    assert result == {"allowed": False, "retry_after": 1}
    assert backend.get("token_bucket:client-1") == state_before_rejection
    
    
    set_clock(monkeypatch, 1005)
    assert limiter.check("client-1") == {"allowed": True}



def test_refill_never_exceeds_bucket_capacity(monkeypatch):
    set_clock(monkeypatch, 1000)
    backend = MemoryBackend()
    limiter = TokenBucket(
        limit=2,
        window_size=10,
        burst_capacity=2,
        backend=backend,
    )

    assert limiter.check("client-1") == {"allowed": True}

    # Leave the bucket idle long enough to refill completely.
    set_clock(monkeypatch, 1100)
    assert limiter.check("client-1") == {"allowed": True}

    # It refilled to 2, then this request spent one token.
    state = backend.get("token_bucket:client-1")
    assert state is not None
    assert state["tokens"] == pytest.approx(1)
    
    
def test_custom_capacity_allows_larger_initial_burst(monkeypatch):
    set_clock(monkeypatch, 1000)
    limiter = TokenBucket(
        limit=2,
        window_size=10,
        burst_capacity=4,
        backend=MemoryBackend(),
    )

    for _ in range(4):
        assert limiter.check("client-1") == {"allowed": True}

    assert limiter.check("client-1") == {
        "allowed": False,
        "retry_after": 5,
    }