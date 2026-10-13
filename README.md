# Django Rate Limiter

This project is under development. It currently provides Django middleware and a per-view decorator, with fixed-window, sliding-window-counter and token-bucket algorithms. Other planned features are not available yet.

## Install

The package is not published yet. During development, install it into your Django project from the local repository, for example:

```bash
uv add --editable ../django-ratelatch
```

Use the path to this repository from your Django project's directory. Once the package is published, installation will use its published package name instead.

## Configure

Add a key function to your Django project. It accepts a request and returns a stable identifier; requests with the same identifier share a rate limit.

```python
# myproject/ratelimit.py
def get_rate_limit_key(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"
    return f"ip:{request.META.get('REMOTE_ADDR', '')}"
```

Configure the limiter in your Django `settings.py`:

```python
import os

RATE_LIMITER = {
    "ALGORITHM" : "fixed_window",  # or "sliding_window_counter" or "token_bucket"
    "LIMIT" : 10,
    "WINDOW_SECONDS" : 60,
    "KEY_FUNCTION" : "myproject.ratelimit.get_rate_limit_key",
    "BACKEND" : "redis",  # or "memory"
    "REDIS_URL" : os.environ["RATE_LIMITER_REDIS_URL"],
    "BURST_CAPACITY": 20,  # optional; token_bucket only, defaults to LIMIT
}
```

- `ALGORITHM`: `fixed_window` or `sliding_window_counter` or `token_bucket`.
- `LIMIT`: For fixed and sliding-window algorithms, the maximum requests allowed per window. For token bucket, the number of tokens replenished per WINDOW_SECONDS
- `WINDOW_SECONDS`: window duration in seconds.
- `KEY_FUNCTION`: dotted path to the function that creates a client key.
- `BACKEND`: `memory` or `redis`. The memory backend is process-local; use Redis when requests are served by multiple processes.
- `REDIS_URL`: Redis connection URL, required when `BACKEND` is `redis`.

## Use as middleware

Add the middleware to your Django project's `MIDDLEWARE` setting:

```python
MIDDLEWARE = [
    # ...
    "django_ratelatch.integrations.middleware.RateLimitMiddleware",
]
```

It applies the configured limit to requests using the configured key function. Rejected requests receive HTTP `429` and a `Retry-After` header.

## Use as a view decorator

Use the decorator on individual views when you want to limit only selected endpoints:

```python
from django_ratelatch.integrations.decorator import rate_limit


@rate_limit()
def my_view(request):
    ...
```

With no argument, it uses `ALGORITHM`, `BACKEND`, `KEY_FUNCTION`, `LIMIT`, and `WINDOW_SECONDS` from `RATE_LIMITER`. To override only the limit and window for a view, pass a rate string:

```python
@rate_limit("10/m")
def another_view(request):
    ...
```

Supported units include seconds (`s`, `sec`), minutes (`m`, `min`), and hours (`h`, `hr`); a multiplier is also supported, such as `30/5m`. The decorator still uses the algorithm, backend, and key function from `RATE_LIMITER`.

Use either the project-wide middleware or the decorator for a given request path. If both run for the same request, both apply a rate-limit check.

## Use with Django REST framework

For a local editable install, add DRF to your consumer project:

```bash
uv add djangorestframework
```

Register the throttle in your Django `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
]

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "django_ratelatch.integrations.drf.RateLimitThrottle",
    ],
}
```

The throttle uses the `RATE_LIMITER` configuration and `KEY_FUNCTION` described above. Throttled requests receive HTTP `429` and a `Retry-After` header.