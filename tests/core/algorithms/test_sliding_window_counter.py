import pytest

from django_ratelatch.backends.memory import MemoryBackend
from django_ratelatch.core.algorithms.sliding_window_counter import (
    SlidingWindowCounter,
)


CLOCK_PATH = "django_ratelatch.core.algorithms.sliding_window_counter.time"


def set_clock(monkeypatch, timestamp):
    monkeypatch.setattr(CLOCK_PATH, lambda: timestamp)


def test_allows_requests_up_to_limit_then_rejects(monkeypatch):
    set_clock(monkeypatch, 1000)

    backend = MemoryBackend()
    limiter = SlidingWindowCounter(limit=3, window_size=10, backend=backend)

    assert limiter.check("client-1") == {"allowed": True}
    assert limiter.check("client-1") == {"allowed": True}
    assert limiter.check("client-1") == {"allowed": True}

    result = limiter.check("client-1")
    assert result["allowed"] is False
    assert result["retry_after"] > 0

    assert backend.get("sliding_window_counter:client-1") == {
        "window_id": 100,
        "previous_count": 0,
        "current_count": 3,
    }


def test_weights_previous_count_but_counts_current_fully(monkeypatch):
    # Window 101 runs from 1010 to 1020. At 1012, 8 of its 10 seconds remain.
    set_clock(monkeypatch, 1012)

    backend = MemoryBackend()
    backend.set(
        "sliding_window_counter:client-1",
        {
            "window_id": 101,
            "previous_count": 5,
            "current_count": 1,
        },
    )
    limiter = SlidingWindowCounter(limit=6, window_size=10, backend=backend)

    # Estimate: 1 current + 5 * 8/10 previous = 5. Allow; current becomes 2.
    assert limiter.check("client-1") == {"allowed": True}
    assert backend.get("sliding_window_counter:client-1") == {
        "window_id": 101,
        "previous_count": 5,
        "current_count": 2,
    }

    # Estimate is now 2 + 5 * 8/10 = 6. Reject without changing state.
    result = limiter.check("client-1")
    assert result["allowed"] is False
    assert backend.get("sliding_window_counter:client-1") == {
        "window_id": 101,
        "previous_count": 5,
        "current_count": 2,
    }


def test_rolls_current_count_into_previous_after_one_window(monkeypatch):
    set_clock(monkeypatch, 1012)  # Current window is 101.

    backend = MemoryBackend()
    backend.set(
        "sliding_window_counter:client-1",
        {
            "window_id": 100,
            "previous_count": 99,  # This older count should be discarded.
            "current_count": 5,
        },
    )
    limiter = SlidingWindowCounter(limit=6, window_size=10, backend=backend)

    assert limiter.check("client-1") == {"allowed": True}
    assert backend.get("sliding_window_counter:client-1") == {
        "window_id": 101,
        "previous_count": 5,
        "current_count": 1,
    }


def test_resets_counts_after_skipping_two_or_more_windows(monkeypatch):
    set_clock(monkeypatch, 1022)  # Current window is 102.

    backend = MemoryBackend()
    backend.set(
        "sliding_window_counter:client-1",
        {
            "window_id": 100,
            "previous_count": 4,
            "current_count": 5,
        },
    )
    limiter = SlidingWindowCounter(limit=6, window_size=10, backend=backend)

    assert limiter.check("client-1") == {"allowed": True}
    assert backend.get("sliding_window_counter:client-1") == {
        "window_id": 102,
        "previous_count": 0,
        "current_count": 1,
    }


@pytest.mark.parametrize(
    ("state", "timestamp", "expected_retry_after"),
    [
        # Previous-window contribution is fading during the current window.
        (
            {"window_id": 101, "previous_count": 8, "current_count": 2},
            1012,
            4,
        ),
        # Current count keeps the estimate at the limit through the boundary.
        (
            {"window_id": 101, "previous_count": 0, "current_count": 6},
            1012,
            9,
        ),
    ],
)
def test_retry_after_for_rejected_request(
    monkeypatch,
    state,
    timestamp,
    expected_retry_after,
):
    set_clock(monkeypatch, timestamp)

    backend = MemoryBackend()
    backend.set("sliding_window_counter:client-1", state)
    limiter = SlidingWindowCounter(limit=6, window_size=10, backend=backend)

    result = limiter.check("client-1")

    assert result == {
        "allowed": False,
        "retry_after": expected_retry_after,
    }
    assert backend.get("sliding_window_counter:client-1") == state


def test_different_keys_have_independent_counts(monkeypatch):
    set_clock(monkeypatch, 1000)

    backend = MemoryBackend()
    limiter = SlidingWindowCounter(limit=1, window_size=10, backend=backend)

    assert limiter.check("client-1") == {"allowed": True}
    assert limiter.check("client-1")["allowed"] is False

    assert limiter.check("client-2") == {"allowed": True}


def test_state_expires_after_it_is_no_longer_needed(monkeypatch):
    set_clock(monkeypatch, 1012)

    monotonic_time = [100.0]
    monkeypatch.setattr(
        "django_ratelatch.backends.memory.monotonic",
        lambda: monotonic_time[0],
    )

    backend = MemoryBackend()
    limiter = SlidingWindowCounter(limit=6, window_size=10, backend=backend)

    assert limiter.check("client-1") == {"allowed": True}
    assert backend.get("sliding_window_counter:client-1") is not None

    # At 1012 in window 101, state expires at the end of window 102:
    # (101 + 2) * 10 = 1030, which is 18 seconds later.
    monotonic_time[0] = 117.9
    assert backend.get("sliding_window_counter:client-1") is not None

    monotonic_time[0] = 118.0
    assert backend.get("sliding_window_counter:client-1") is None


@pytest.mark.parametrize(
    ("limit", "window_size"),
    [
        (True, 10),
        (5, False),
        (1.5, 10),
        (5, "10"),
    ],
)
def test_rejects_non_integer_settings(limit, window_size):
    with pytest.raises(TypeError):
        SlidingWindowCounter(
            limit=limit,
            window_size=window_size,
            backend=MemoryBackend(),
        )


@pytest.mark.parametrize(
    ("limit", "window_size"),
    [
        (0, 10),
        (-1, 10),
        (5, 0),
        (5, -10),
    ],
)
def test_rejects_non_positive_settings(limit, window_size):
    with pytest.raises(ValueError):
        SlidingWindowCounter(
            limit=limit,
            window_size=window_size,
            backend=MemoryBackend(),
        )