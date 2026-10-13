import math
from time import time


class FixedWindow:
    
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
            window_end = (current_window + 1) * self.window_size
            timeout = math.ceil(window_end - now)

            if state is None or state["window_id"] != current_window:
                new_state = {
                    "window_id": current_window,
                    "request_count": 1,
                }
                return new_state, {"allowed": True}, timeout

            if state["request_count"] >= self.limit:
                return None, {
                    "allowed": False,
                    "retry_after": timeout,
                    
                }, None

            new_state = {
                "window_id": current_window,
                "request_count": state["request_count"] + 1,
            }
            return new_state, {"allowed": True}, timeout
            
            
        # return self.backend.update(key, updater)
        return self.backend.update(f"fixed_window:{key}", updater)