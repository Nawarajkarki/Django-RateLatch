import math
from time import time


class TokenBucket:
    def __init__(self, limit, window_size, backend, burst_capacity=None):
        if (
            isinstance(limit, bool)
            or isinstance(window_size, bool)
            or not isinstance(limit, int)
            or not isinstance(window_size, int)
        ):
            raise TypeError("limit and window_size must be integers")

        if limit <= 0 or window_size <= 0:
            raise ValueError("limit and window_size must be greater than zero")

        if burst_capacity is None:
            burst_capacity = limit

        if isinstance(burst_capacity, bool) or not isinstance(burst_capacity, int):
            raise TypeError("burst_capacity must be an integer")

        if burst_capacity <= 0:
            raise ValueError("burst_capacity must be greater than zero")

        self.limit = limit
        self.window_size = window_size
        self.burst_capacity = burst_capacity
        self.refill_rate = limit / window_size
        self.backend = backend

    def check(self, key):
        def updater(state):
            now = time()

            if state is None:
                tokens = float(self.burst_capacity)
                last_refill_time = now
            else:
                tokens = min(
                    float(self.burst_capacity),
                    float(state["tokens"]),
                )
                last_refill_time = float(state["last_refill_time"])

            # Avoid moving the saved clock backwards if the system clock shifts.
            effective_now = max(now, last_refill_time)
            elapsed = effective_now - last_refill_time

            tokens = min(
                float(self.burst_capacity),
                tokens + elapsed * self.refill_rate,
            )

            if tokens < 1:
                retry_after = math.ceil((1 - tokens) / self.refill_rate)
                return None, {
                    "allowed": False,
                    "retry_after": max(1, retry_after),
                }, None

            tokens -= 1

            new_state = {
                "tokens": tokens,
                "last_refill_time": effective_now,
            }

            # The state can expire once the bucket would be full;
            # a missing state is equivalent to a full bucket.
            seconds_until_full = (
                self.burst_capacity - tokens
            ) / self.refill_rate
            timeout = max(1, math.ceil(seconds_until_full))

            return new_state, {"allowed": True}, timeout

        return self.backend.update(f"token_bucket:{key}", updater)