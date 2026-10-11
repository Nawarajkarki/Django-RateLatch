import os
import uuid

import pytest

from django.http import HttpResponse
from django.test import RequestFactory


from django_ratelimiter.integrations.middleware import RateLimitMiddleware
from django_ratelimiter.exceptions import RateLimiterBackendError


def configure_test_middleware(settings, monkeypatch, *, limit):
    settings.RATE_LIMITER = {
        "ALGORITHM": "fixed_window",
        "LIMIT": limit,
        "WINDOW_SECONDS": 60,
        "KEY_FUNCTION": "unused.in.test",
        "BACKEND" : "memory"
    }

    # Keep the clock fixed so requests stay in the same window.
    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.fixed_window.time",
        lambda: 1000,
    )

    # Give every request from this test client the same rate-limit key.
    monkeypatch.setattr(
        "django_ratelimiter.integrations.middleware.import_string",
        lambda dotted_path: lambda request: "ip:127.0.0.1",
    )


@pytest.mark.skipif(
    not os.getenv("RATE_LIMITER_REDIS_URL"),
    reason="Set RATE_LIMITER_REDIS_URL to run the Redis middleware test",
)

def test_middleware_uses_redis(settings, monkeypatch):
    key = f"ip:{uuid.uuid4().hex}"

    settings.RATE_LIMITER = {
        "ALGORITHM": "fixed_window",
        "LIMIT": 1,
        "WINDOW_SECONDS": 60,
        "KEY_FUNCTION": "unused.in.test",
        "BACKEND": "redis",
        "REDIS_URL": os.environ["RATE_LIMITER_REDIS_URL"],
    }

    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.fixed_window.time",
        lambda: 1000,
    )
    monkeypatch.setattr(
        "django_ratelimiter.integrations.middleware.import_string",
        lambda dotted_path: lambda request: key,
    )

    middleware = RateLimitMiddleware(lambda request: HttpResponse("OK"))
    request = RequestFactory().get("/")

    assert middleware(request).status_code == 200
    assert middleware(request).status_code == 429
    
    
    

def test_allowed_request_reaches_view(settings, monkeypatch):
    configure_test_middleware(settings, monkeypatch, limit=1)
    view_calls = []

    def get_response(request):
        view_calls.append(request)
        return HttpResponse("View response")

    middleware = RateLimitMiddleware(get_response)
    request = RequestFactory().get("/")

    response = middleware(request)

    assert response.status_code == 200
    assert len(view_calls) == 1


def test_rejected_request_returns_429_and_does_not_reach_view(
    settings, monkeypatch
):
    configure_test_middleware(settings, monkeypatch, limit=1)
    view_calls = []

    def get_response(request):
        view_calls.append(request)
        return HttpResponse("View response")

    middleware = RateLimitMiddleware(get_response)
    request = RequestFactory().get("/")

    first_response = middleware(request)
    second_response = middleware(request)

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response["Retry-After"] == "20"
    assert len(view_calls) == 1
    
    
    
@pytest.mark.parametrize(
    ("fail_open", "expected_status", "expected_view_calls"),
    [
        (False, 503, 0),
        (True, 200, 1),
    ],
)
def test_middleware_backend_failure_policy(
    settings,
    monkeypatch,
    fail_open,
    expected_status,
    expected_view_calls,
):
    configure_test_middleware(settings, monkeypatch, limit=1)
    settings.RATE_LIMITER = {
        **settings.RATE_LIMITER,
        "FAIL_OPEN": fail_open,
    }

    class FailingLimiter:
        def check(self, key):
            raise RateLimiterBackendError("test backend failure")

    monkeypatch.setattr(
        "django_ratelimiter.integrations.middleware.build_limiter",
        lambda **kwargs: FailingLimiter(),
    )

    view_calls = []

    def get_response(request):
        view_calls.append(request)
        return HttpResponse("View response")

    middleware = RateLimitMiddleware(get_response)
    response = middleware(RequestFactory().get("/"))

    assert response.status_code == expected_status
    assert len(view_calls) == expected_view_calls