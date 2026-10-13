
### _state dict format will be 
# { # for fixed window algo
#     "user_123" : {
#         "window_id" = 1223,
#         "request_count" = 12
#     }

# { # sliding window counter
#     "user1" : {
#     "window_id": 16,
#     "current_count": 2,
#     "previous_count": 4,
# }
# }


from threading import Lock
from time import monotonic


class MemoryBackend:
    def __init__(self):
        self._store = {}
        self._lock = Lock()     
        self._locks = {}
        self._expires_at = {}


    def get(self, key):
        with self._lock:
            expires_at = self._expires_at.get(key)
            
            if expires_at is not None and monotonic() >= expires_at:
                self._store.pop(key, None)
                self._expires_at.pop(key, None)
                return None
            
            return self._store.get(key)
    
    def set(self, key, state, timeout=None):
        with self._lock:
            self._store[key] = state

            if timeout is None:
                self._expires_at.pop(key, None)
            else:
                self._expires_at[key] = monotonic() + timeout
                

    def lock(self, key):
        with self._lock:
            if key not in self._locks:
                self._locks[key] = Lock()

            return self._locks[key]
        
    
    
    def update(self, key, updater):
        with self.lock(key):
            state = self.get(key)
            new_state, result, timeout = updater(state)

            if new_state is not None:
                self.set(key, new_state, timeout=timeout)

            return result