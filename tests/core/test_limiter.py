import pytest

from django.core.exceptions import ImproperlyConfigured

from django_ratelimiter.backends.memory import MemoryBackend
from django_ratelimiter.core.limiter import build_limiter
from django_ratelimiter.core.algorithms.fixed_window import FixedWindow
from django_ratelimiter.core.algorithms.sliding_window_counter import SlidingWindowCounter
from django_ratelimiter.core.algorithms.token_bucket import TokenBucket


def test_builds_fixed_window():
    backend = MemoryBackend()
    config = {
        "ALGORITHM": "fixed_window",
        "LIMIT": 2,
        "WINDOW_SECONDS": 60,
    }

    limiter = build_limiter(config, backend)

    assert isinstance(limiter, FixedWindow)
    assert limiter.backend is backend



@pytest.mark.parametrize("algorithm", [ "sliding_window", "sliding_window_log",  "anything else"])
def test_build_limiter_rejects_unimplemented_algorithms(algorithm):
    config = {
        "ALGORITHM": algorithm,
        "LIMIT": 2,
        "WINDOW_SECONDS": 60,
    }

    with pytest.raises(ImproperlyConfigured, match="Unsupported rate-limit algorithm"):
        build_limiter(config=config, backend=MemoryBackend())



def test_builds_sliding_window_counter():
    backend = MemoryBackend()
    config = {
        "ALGORITHM": "sliding_window_counter",
        "LIMIT": 2,
        "WINDOW_SECONDS": 60,
    }

    limiter = build_limiter(config, backend)

    assert isinstance(limiter, SlidingWindowCounter)
    assert limiter.backend is backend



def test_builds_token_buckets():
    backend = MemoryBackend()
    config = {
        "ALGORITHM": "token_bucket",
        "LIMIT": 2,
        "WINDOW_SECONDS": 60,
        "BURST_CAPACITY" : 20
    }

    limiter = build_limiter(config, backend)

    assert isinstance(limiter, TokenBucket)
    assert limiter.backend is backend
    assert limiter.burst_capacity == 20
    
def test_token_bucket_defaults_burst_capacity_to_limit():
    backend = MemoryBackend()
    config = {
        "ALGORITHM": "token_bucket",
        "LIMIT": 2,
        "WINDOW_SECONDS": 10,
    }

    limiter = build_limiter(config, backend)

    assert isinstance(limiter, TokenBucket)
    assert limiter.burst_capacity == 2