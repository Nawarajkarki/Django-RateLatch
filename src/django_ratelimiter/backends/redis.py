import json
import random
import time

from redis.exceptions import RedisError, WatchError
from django_ratelimiter.exceptions import RateLimiterBackendError


MAX_UPDATE_ATTEMPTS = 25
MAX_RETRY_DELAY_SECONDS = 0.01


class RedisBackend:
    def __init__(self, client, key_prefix="django_ratelimiter"):
        self.client = client
        self.key_prefix = key_prefix.rstrip(":")
        
    def _redis_key(self, key):
        return f"{self.key_prefix}:{key}"
    
    def get(self, key):
        try:
            raw_state = self.client.get(self._redis_key(key))
        except RedisError as exc:
            raise RateLimiterBackendError("Redis operation failed.") from exc
                
        if raw_state is None:
            return None
        
        return json.loads(raw_state)

    def set(self, key, state, timeout = None):
        options = {}
        if timeout is not None:
            options["ex"] = timeout
        
        try:
            self.client.set(
                self._redis_key(key),
                json.dumps(state),
                **options,
            )
        except RedisError as exc:
            raise RateLimiterBackendError("Redis operation failed.") from exc
        
    
    
    def update(self, key, updater):
        redis_key = self._redis_key(key)

        for attempt in range(MAX_UPDATE_ATTEMPTS):
            try:
                with self.client.pipeline() as pipe:
                    pipe.watch(redis_key)

                    raw_state = pipe.get(redis_key)
                    state = None if raw_state is None else json.loads(raw_state)

                    new_state, result, timeout = updater(state)

                    if new_state is None:
                        pipe.unwatch()
                        return result

                    pipe.multi()

                    options = {}
                    if timeout is not None:
                        options["ex"] = timeout

                    pipe.set(redis_key, json.dumps(new_state), **options)
                    pipe.execute()

                    return result

            except WatchError as exc:
                if attempt == MAX_UPDATE_ATTEMPTS - 1:
                    raise RateLimiterBackendError(
                        "Redis update conflicted too many times."
                    ) from exc

                delay_cap = min(
                    0.0005 * (2 ** attempt),
                    MAX_RETRY_DELAY_SECONDS,
                )
                time.sleep(random.uniform(0, delay_cap))
            
            except RedisError as exc:
                raise RateLimiterBackendError(
                    "Redis operation failed."
                ) from exc
            
            