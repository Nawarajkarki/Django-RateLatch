from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.throttling import BaseThrottle

from django_ratelimiter.backends.factory import build_backend
from django_ratelimiter.core.limiter import build_limiter
from django_ratelimiter.exceptions import RateLimiterBackendError


class RateLimiterUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Rate limiter temporarily unavailable."
    default_code = "rate_limiter_unavailable"


@lru_cache(maxsize=None)
def _build_configured_limiter(
    algorithm,
    limit,
    window_seconds,
    burst_capacity,
    backend_name,
    redis_url,
    redis_socket_timeout,
    redis_connect_timeout,
):
    """Build one limiter per configuration, reusing its backend across requests."""
    config = {
        "ALGORITHM": algorithm,
        "LIMIT": limit,
        "WINDOW_SECONDS": window_seconds,
        "BACKEND": backend_name,
    }

    if burst_capacity is not None:
        config["BURST_CAPACITY"] =  burst_capacity
    
    if backend_name == "redis":
        config["REDIS_URL"] = redis_url
        config["REDIS_SOCKET_TIMEOUT"] = redis_socket_timeout
        config["REDIS_CONNECT_TIMEOUT"] = redis_connect_timeout

    backend = build_backend(config)
    return build_limiter(config=config, backend=backend)


def _get_configured_limiter(config):
    backend_name = config["BACKEND"].strip().lower()

    return _build_configured_limiter(
        config["ALGORITHM"],
        config["LIMIT"],
        config["WINDOW_SECONDS"],
        config.get("BURST_CAPACITY"),
        backend_name,
        config.get("REDIS_URL"),
        config.get("REDIS_SOCKET_TIMEOUT", 1.0),
        config.get("REDIS_CONNECT_TIMEOUT", 1.0),
    )


class RateLimitThrottle(BaseThrottle):
    def __init__(self):
        config = settings.RATE_LIMITER.copy()

        self.fail_open = config.get("FAIL_OPEN", False)
        if not isinstance(self.fail_open, bool):
            raise ImproperlyConfigured(
                "RATE_LIMITER['FAIL_OPEN'] must be a boolean."
            )

        self.key_function = import_string(config["KEY_FUNCTION"])
        self.limiter = _get_configured_limiter(config)
        self.retry_after = None

    def allow_request(self, request, view):
        key = self.key_function(request)

        try:
            decision = self.limiter.check(key)
        except RateLimiterBackendError as exc:
            if self.fail_open:
                return True

            raise RateLimiterUnavailable() from exc

        if decision["allowed"]:
            return True

        self.retry_after = decision.get("retry_after")
        return False

    def wait(self):
        return self.retry_after
    