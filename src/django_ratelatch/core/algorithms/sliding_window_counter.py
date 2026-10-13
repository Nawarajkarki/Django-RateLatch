import math
from time import time


class SlidingWindowCounter():
    
    def __init__(self, limit, window_size, backend):
        
        if (
            isinstance(limit, bool)
            or isinstance(window_size, bool)
            or not isinstance(limit, int)
            or not isinstance(window_size, int)
        ):
            raise TypeError("limit and window_size must be integers")
        
        
        if limit <= 0 or window_size <= 0:
            raise ValueError("limit and window_size must be greater than zero")
        
        self.limit = limit
        self.window_size = window_size
        self.backend = backend
        
    
    def check(self, key):
        def updater(state):
            now = time()
            current_window = int(now // self.window_size)
            window_start = current_window * self.window_size
            elapsed = now - window_start

            # Convert saved counts to counts for the current and previous
            if state is None:
                previous_count = 0
                current_count = 0
            elif state["window_id"] == current_window:
                previous_count = state["previous_count"]
                current_count = state["current_count"]
            elif state["window_id"] == current_window - 1:
                previous_count = state["current_count"]
                current_count = 0
            else:
                # The state is too old, or its window is in the future.
                previous_count = 0
                current_count = 0

            previous_window_weight = (
                self.window_size - elapsed
            ) / self.window_size

            estimated_count = (
                current_count
                + previous_count * previous_window_weight
            )

            """
            keep this state through the following window, because this window's 
            current_count becomes the next window's previous_count
            """
            next_window_end = (current_window + 2) * self.window_size
            timeout = math.ceil(next_window_end - now)

            if estimated_count >= self.limit:
                retry_after = self._retry_after(
                    current_count=current_count,
                    previous_count=previous_count,
                    elapsed=elapsed,
                    estimated_count=estimated_count,
                )
                return None, {
                    "allowed": False,
                    "retry_after": retry_after,
                }, None

            new_state = {
                "window_id": current_window,
                "current_count": current_count + 1,
                "previous_count": previous_count,
            }
            return new_state, {"allowed": True}, timeout

        return self.backend.update(f"sliding_window_counter:{key}", updater)

    def _retry_after(
        self,
        *,
        current_count,
        previous_count,
        elapsed,
        estimated_count,
    ):
        if current_count < self.limit:
            # The previous count is fading out during this window.
            seconds_until_below_limit = (
                (estimated_count - self.limit)
                * self.window_size
                / previous_count
            )
        else:
            # The estimate can't fall below the limit until the next window.
            seconds_to_next_window = self.window_size - elapsed
            seconds_into_next_window = (
                self.window_size
                * (current_count - self.limit)
                / current_count
            )
            seconds_until_below_limit = (
                seconds_to_next_window + seconds_into_next_window
            )

        return max(1, math.floor(seconds_until_below_limit) + 1)
    
    