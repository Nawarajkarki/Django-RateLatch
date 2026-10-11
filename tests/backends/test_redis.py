
import uuid
import pytest

from redis import Redis
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock
from redis.exceptions import ResponseError, TimeoutError as RedisTimeoutError, WatchError

from django_ratelimiter.backends.redis import RedisBackend, MAX_UPDATE_ATTEMPTS
from django_ratelimiter.core.algorithms.fixed_window import FixedWindow
from django_ratelimiter.core.algorithms.sliding_window_counter import SlidingWindowCounter
from django_ratelimiter.exceptions import RateLimiterBackendError

from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    ResponseError,
    TimeoutError as RedisTimeoutError,
    WatchError,
)




@pytest.fixture
def redis_backend():
    client = Redis(
        host="localhost",
        port=6379,
        db=15,
        protocol=2,
        decode_responses=True,
    )
    client.ping()

    prefix = f"test-ratelimiter-{uuid.uuid4().hex}"
    backend = RedisBackend(client, key_prefix=prefix)

    yield backend

    keys = list(client.scan_iter(match=f"{prefix}:*"))
    if keys:
        client.delete(*keys)
    client.close()
    
    
def test_missing_key_returns_none(redis_backend):
    assert redis_backend.get("missing") is None


def test_set_and_get_round_trip(redis_backend):
    state = {"window_id": 12, "request_count": 2}

    redis_backend.set("client-1", state)

    assert redis_backend.get("client-1") == state


def test_set_applies_timeout(redis_backend):
    redis_backend.set("client-1", {"request_count": 1}, timeout=2)

    ttl = redis_backend.client.ttl(redis_backend._redis_key("client-1"))
    assert 0 < ttl <= 2
    
    
    


def test_fixed_window_uses_redis_backend(redis_backend, monkeypatch):
    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.fixed_window.time",
        lambda: 1000,
    )

    limiter = FixedWindow(
        limit=2,
        window_size=60,
        backend=redis_backend,
    )

    assert limiter.check("client-1") == {"allowed": True}
    assert limiter.check("client-1") == {"allowed": True}
    assert limiter.check("client-1") == {
        "allowed": False,
        "retry_after": 20,
    }

    state = redis_backend.get("client-1")
    assert state == {"window_id": 16, "request_count": 2}
    
    
    


def test_concurrent_requests_do_not_exceed_limit_with_redis(
    redis_backend,
    monkeypatch,
):
    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.fixed_window.time",
        lambda: 1000,
    )

    limit = 10
    limiter = FixedWindow(
        limit=limit,
        window_size=60,
        backend=redis_backend,
    )

    with ThreadPoolExecutor(max_workers=20) as executor:
        decisions = list(
            executor.map(
                lambda _: limiter.check("client-1"),
                range(100),
            )
        )

    allowed_count = sum(decision["allowed"] for decision in decisions)
    assert allowed_count == limit

    state = redis_backend.get("client-1")
    assert state is not None
    assert state["request_count"] == limit
    
    
    
    


def test_sliding_window_counter_uses_redis_backend(
    redis_backend,
    monkeypatch,
):
    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.sliding_window_counter.time",
        lambda: 1012,
    )

    redis_backend.set(
        "client-1",
        {
            "window_id": 101,
            "previous_count": 5,
            "current_count": 1,
        },
        timeout=30,
    )

    limiter = SlidingWindowCounter(
        limit=6,
        window_size=10,
        backend=redis_backend,
    )

    assert limiter.check("client-1") == {"allowed": True}
    assert redis_backend.get("client-1") == {
        "window_id": 101,
        "previous_count": 5,
        "current_count": 2,
    }

    result = limiter.check("client-1")
    assert result["allowed"] is False
    assert redis_backend.get("client-1") == {
        "window_id": 101,
        "previous_count": 5,
        "current_count": 2,
    }
    
@pytest.mark.parametrize(
    "error",
    [
        ResponseError("OOM command not allowed"),
        RedisTimeoutError("Redis timed out"),
    ],
)
def test_get_wraps_redis_errors(error):
    client = MagicMock()
    client.get.side_effect = error
    backend = RedisBackend(client)

    with pytest.raises(RateLimiterBackendError):
        backend.get("client-1")


@pytest.mark.parametrize(
    "error",
    [
        ResponseError("OOM command not allowed"),
        RedisTimeoutError("Redis timed out"),
    ],
)
def test_set_wraps_redis_errors(error):
    client = MagicMock()
    client.set.side_effect = error
    backend = RedisBackend(client)

    with pytest.raises(RateLimiterBackendError):
        backend.set("client-1", {"request_count": 1})


@pytest.mark.parametrize(
    "error",
    [
        ResponseError("OOM command not allowed"),
        RedisTimeoutError("Redis timed out"),
        RedisConnectionError("Redis is unavailable"),
    ],
)
def test_update_wraps_redis_errors(error):
    client = MagicMock()
    pipe = client.pipeline.return_value.__enter__.return_value
    pipe.get.return_value = None
    pipe.execute.side_effect = error
    backend = RedisBackend(client)

    def updater(state):
        return {"request_count": 1}, {"allowed": True}, 60

    with pytest.raises(RateLimiterBackendError):
        backend.update("client-1", updater)
        
        
        
def test_update_retries_watch_error():
    client = MagicMock()
    pipe = client.pipeline.return_value.__enter__.return_value
    pipe.watch.side_effect = [WatchError(), None]
    pipe.get.return_value = None
    backend = RedisBackend(client)

    def updater(state):
        return {"request_count": 1}, {"allowed": True}, 60

    result = backend.update("client-1", updater)

    assert result == {"allowed": True}
    assert pipe.watch.call_count == 2
    assert pipe.execute.call_count == 1



def test_concurrent_requests_from_independent_redis_clients(
    redis_backend,
    monkeypatch,
):
    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.fixed_window.time",
        lambda: 1000,
    )

    second_client = Redis(
        host="localhost",
        port=6379,
        db=15,
        protocol=2,
        decode_responses=True,
    )
    second_client.ping()

    second_backend = RedisBackend(
        second_client,
        key_prefix=redis_backend.key_prefix,
    )

    limit = 10
    limiters = [
        FixedWindow(limit=limit, window_size=60, backend=redis_backend),
        FixedWindow(limit=limit, window_size=60, backend=second_backend),
    ]

    try:
        with ThreadPoolExecutor(max_workers=20) as executor:
            decisions = list(
                executor.map(
                    lambda i: limiters[i % 2].check("client-1"),
                    range(100),
                )
            )
    finally:
        second_client.close()

    assert sum(decision["allowed"] for decision in decisions) == limit

    state = redis_backend.get("client-1")
    assert state["request_count"] == limit

def test_update_stops_after_too_many_watch_errors():
    client = MagicMock()
    pipe = client.pipeline.return_value.__enter__.return_value
    pipe.watch.side_effect = WatchError()
    backend = RedisBackend(client)

    def updater(state):
        return {"request_count": 1}, {"allowed": True}, 60

    with pytest.raises(RateLimiterBackendError, match="conflicted too many times"):
        backend.update("client-1", updater)

    assert pipe.watch.call_count == MAX_UPDATE_ATTEMPTS