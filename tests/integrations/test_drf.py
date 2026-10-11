import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from django_ratelimiter.exceptions import RateLimiterBackendError
from django_ratelimiter.integrations import drf
from django_ratelimiter.integrations.drf import RateLimitThrottle

from django_ratelimiter.integrations.drf import RateLimitThrottle


def key_from_client_header(request):
    return request.META["HTTP_X_CLIENT_ID"]


@pytest.fixture(autouse=True)
def clear_limiter_cache():
    # The throttle intentionally shares its limiter across request instances.
    # Clear it between tests so test state doesn't leak.
    drf._build_configured_limiter.cache_clear()
    yield
    drf._build_configured_limiter.cache_clear()


def configure_drf(settings, monkeypatch, *, limit=1, fail_open=False):
    settings.RATE_LIMITER = {
        "ALGORITHM": "fixed_window",
        "LIMIT": limit,
        "WINDOW_SECONDS": 60,
        "KEY_FUNCTION": "unused.in.test",
        "BACKEND": "memory",
        "FAIL_OPEN": fail_open,
    }

    # Give each request the same client key in these tests.
    monkeypatch.setattr(
        "django_ratelimiter.integrations.drf.import_string",
        lambda dotted_path: lambda request: "ip:127.0.0.1",
    )

    # Keep all requests in the same fixed window.
    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.fixed_window.time",
        lambda: 1000,
    )


def test_api_view_allows_within_limit_then_returns_429_and_retry_after(
    settings,
    monkeypatch,
):
    configure_drf(settings, monkeypatch, limit=1)

    class ExampleView(APIView):
        throttle_classes = [RateLimitThrottle]

        def get(self, request):
            return Response({"message": "ok"})

    view = ExampleView.as_view()
    request_factory = APIRequestFactory()

    first_response = view(request_factory.get("/example/"))
    second_response = view(request_factory.get("/example/"))

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response["Retry-After"] == "20"


def test_function_based_api_view_uses_throttle(settings, monkeypatch):
    configure_drf(settings, monkeypatch, limit=1)

    @api_view(["GET"])
    @throttle_classes([RateLimitThrottle])
    def example_view(request):
        return Response({"message": "ok"})

    request_factory = APIRequestFactory()

    first_response = example_view(request_factory.get("/example/"))
    second_response = example_view(request_factory.get("/example/"))

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response["Retry-After"] == "20"


def test_viewset_uses_throttle(settings, monkeypatch):
    configure_drf(settings, monkeypatch, limit=1)

    class ExampleViewSet(ViewSet):
        throttle_classes = [RateLimitThrottle]

        def list(self, request):
            return Response({"message": "ok"})

    view = ExampleViewSet.as_view({"get": "list"})
    request_factory = APIRequestFactory()

    first_response = view(request_factory.get("/example/"))
    second_response = view(request_factory.get("/example/"))

    assert first_response.status_code == 200
    assert second_response.status_code == 429


@pytest.mark.parametrize(
    ("fail_open", "expected_status", "expected_view_calls"),
    [
        (False, 503, 0),
        (True, 200, 1),
    ],
)
def test_backend_failure_policy(
    settings,
    monkeypatch,
    fail_open,
    expected_status,
    expected_view_calls,
):
    configure_drf(settings, monkeypatch, fail_open=fail_open)

    class FailingLimiter:
        def check(self, key):
            raise RateLimiterBackendError("test backend failure")

    monkeypatch.setattr(
        drf,
        "build_limiter",
        lambda **kwargs: FailingLimiter(),
    )

    view_calls = []

    class ExampleView(APIView):
        throttle_classes = [RateLimitThrottle]

        def get(self, request):
            view_calls.append(request)
            return Response({"message": "ok"})

    response = ExampleView.as_view()(APIRequestFactory().get("/example/"))

    assert response.status_code == expected_status
    assert len(view_calls) == expected_view_calls


def test_fail_open_must_be_boolean(settings):
    settings.RATE_LIMITER = {
        "ALGORITHM": "fixed_window",
        "LIMIT": 1,
        "WINDOW_SECONDS": 60,
        "KEY_FUNCTION": "unused.in.test",
        "BACKEND": "memory",
        "FAIL_OPEN": "yes",
    }

    with pytest.raises(ImproperlyConfigured):
        RateLimitThrottle()

def test_default_rest_framework_setting_enables_throttle(settings, monkeypatch):
    configure_drf(settings, monkeypatch, limit=1)

    class ExampleView(APIView):
        def get(self, request):
            return Response({"message": "ok"})

    view = ExampleView.as_view()
    request_factory = APIRequestFactory()

    first_response = view(request_factory.get("/example/"))
    second_response = view(request_factory.get("/example/"))

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response["Retry-After"] == "20"
    
    
def test_configured_key_function_receives_drf_request(settings, monkeypatch):
    settings.RATE_LIMITER = {
        "ALGORITHM": "fixed_window",
        "LIMIT": 1,
        "WINDOW_SECONDS": 60,
        "KEY_FUNCTION": "tests.integrations.test_drf.key_from_client_header",
        "BACKEND": "memory",
    }

    monkeypatch.setattr(
        "django_ratelimiter.core.algorithms.fixed_window.time",
        lambda: 1000,
    )

    class ExampleView(APIView):
        throttle_classes = [RateLimitThrottle]

        def get(self, request):
            return Response({"message": "ok"})

    view = ExampleView.as_view()
    request_factory = APIRequestFactory()

    client_a_first = view(
        request_factory.get("/example/", HTTP_X_CLIENT_ID="client-a")
    )
    client_b_first = view(
        request_factory.get("/example/", HTTP_X_CLIENT_ID="client-b")
    )
    client_a_second = view(
        request_factory.get("/example/", HTTP_X_CLIENT_ID="client-a")
    )
    client_b_second = view(
        request_factory.get("/example/", HTTP_X_CLIENT_ID="client-b")
    )

    assert client_a_first.status_code == 200
    assert client_b_first.status_code == 200
    assert client_a_second.status_code == 429
    assert client_b_second.status_code == 429