from unittest.mock import Mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from redis import Redis

from django_ratelimiter.backends import factory


@pytest.fixture(autouse=True)
def clear_redis_backend_cache():
    # The factory caches Redis backends, so keep each test isolated.
    factory._redis_backend_for_url.cache_clear()
    yield
    factory._redis_backend_for_url.cache_clear()


@pytest.mark.parametrize(
    ("extra_settings", "expected_socket_timeout", "expected_connect_timeout"),
    [
        ({}, 1.0, 1.0),
        (
            {
                "REDIS_SOCKET_TIMEOUT": 0.25,
                "REDIS_CONNECT_TIMEOUT": 0.75,
            },
            0.25,
            0.75,
        ),
    ],
)
def test_build_backend_passes_timeouts_to_redis(
    monkeypatch,
    extra_settings,
    expected_socket_timeout,
    expected_connect_timeout,
):
    fake_client = object()
    mock_from_url = Mock(return_value=fake_client)
    monkeypatch.setattr(Redis, "from_url", mock_from_url)

    config = {
        "BACKEND": "redis",
        "REDIS_URL": "redis://example.test/0",
        **extra_settings,
    }

    factory.build_backend(config)

    mock_from_url.assert_called_once_with(
        "redis://example.test/0",
        protocol=2,
        socket_timeout=expected_socket_timeout,
        socket_connect_timeout=expected_connect_timeout,
    )


@pytest.mark.parametrize(
    "bad_value",
    [0, -1, True, "1", float("inf"), float("nan")],
)
@pytest.mark.parametrize(
    "setting_name",
    ["REDIS_SOCKET_TIMEOUT", "REDIS_CONNECT_TIMEOUT"],
)
def test_build_backend_rejects_invalid_timeouts(setting_name, bad_value):
    config = {
        "BACKEND": "redis",
        "REDIS_URL": "redis://example.test/0",
        setting_name: bad_value,
    }

    with pytest.raises(ImproperlyConfigured):
        factory.build_backend(config)