import math
from functools import lru_cache

from django.core.exceptions import ImproperlyConfigured
from django_ratelimiter.backends.memory import MemoryBackend


def _get_timeout(config, setting_name):
    value = config.get(setting_name, 1.0)

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ImproperlyConfigured(
            f"{setting_name} must be a positive number of seconds."
        )

    return float(value)


@lru_cache(maxsize=8)
def _redis_backend_for_url(
    redis_url,
    socket_timeout,
    socket_connect_timeout,
):
    try:
        from redis import Redis
        from django_ratelimiter.backends.redis import RedisBackend
    except ImportError as exc:
        raise ImproperlyConfigured(
            "The Redis backend requires the 'redis' extra. "
            "Install django-ratelimiter with Redis support."
        ) from exc

    client = Redis.from_url(
        redis_url,
        protocol=2,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
    )
    return RedisBackend(client)



def build_backend(config):
    normalized_backend = config['BACKEND'].strip().lower()
    
    if normalized_backend == "memory":
        return MemoryBackend()
    
    if normalized_backend == "redis":
        return _redis_backend_for_url(
            config["REDIS_URL"],
            _get_timeout(config, "REDIS_SOCKET_TIMEOUT"),
            _get_timeout(config, "REDIS_CONNECT_TIMEOUT"),
        )
    
    raise ImproperlyConfigured(
        f"Unsupported rate-limiter backend: {normalized_backend}"
    )
