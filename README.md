# Django RateLatch

A configurable Django rate-limiting library with **middleware**, **per-view decorators**, and **Django REST Framework** throttle support.

Choose **fixed-window**, **sliding-window-counter**, or **token-bucket** rate limiting. Store state in **memory** for single-process use, or in **Redis** for shared use across processes and servers.

Use it to apply limits across a Django project, selected views, or DRF endpoints.


## Features

- Apply a rate limit across Django requests with middleware.
- Apply limits to selected views with a decorator.
- Integrate with Django REST Framework using a throttle class.
- Choose between fixed-window, sliding-window-counter, and token-bucket algorithms.
- Use in-memory or Redis storage.
- Return HTTP `429` responses with a `Retry-After` header when a request is rejected.
- Configure behavior for rate-limiter backend failures.




## Requirements

- Python 3.11 or newer
- Django 5.2 or newer

The optional Django REST Framework integration requires Django REST Framework.
The optional Redis backend requires the `redis` Python client and a reachable Redis
server.

## Installation

With pip:

```bash
python -m pip install django-ratelatch
```

With uv:

```bash
uv add django-ratelatch
```

### Optional integrations

Install the Redis extra if using the Redis backend:

```bash
python -m pip install "django-ratelatch[redis]"
uv add "django-ratelatch[redis]"
```

Install the DRF extra if using the Django REST Framework integration:

```bash
python -m pip install "django-ratelatch[drf]"
uv add "django-ratelatch[drf]"
```

To install both extras:

```bash
python -m pip install "django-ratelatch[redis,drf]"
uv add "django-ratelatch[redis,drf]"
```

The Redis extra installs the Python client. It does not install or run a Redis server.

## Configuration

Define a key function in your Django project. Requests that return the same key share a
rate limit.

```python
# my_project/rate_limit_key.py
def get_rate_limit_key(request):
    if request.user.is_authenticated:
        return f"user:{request.user.pk}"

    return f"ip:{request.META.get('REMOTE_ADDR', '')}"
```

Add a `RATE_LIMITER` setting to your Django project's `settings.py`:

```python
RATE_LIMITER = {
    "ALGORITHM": "fixed_window",
    "LIMIT": 10,
    "WINDOW_SECONDS": 60,
    "KEY_FUNCTION": "my_project.rate_limit_key.get_rate_limit_key",
    "BACKEND": "memory",
}
```

`KEY_FUNCTION` is a dotted Python path to a function that accepts a Django request and
returns a client key.

### Use Redis storage

For applications served by multiple processes or servers, configure Redis so they share
rate-limit state:

```python
import os

RATE_LIMITER["BACKEND"] = "redis"
RATE_LIMITER["REDIS_URL"] = os.environ["RATE_LIMITER_REDIS_URL"]
```

Set `RATE_LIMITER_REDIS_URL` in the environment where Django runs, for example:

```text
redis://localhost:6379/0
```

Optional Redis connection timeouts are specified in seconds and default to `1.0`:

```python
RATE_LIMITER["REDIS_SOCKET_TIMEOUT"] = 1.0
RATE_LIMITER["REDIS_CONNECT_TIMEOUT"] = 1.0
```

### Configuration options

| Setting | Meaning |
| --- | --- |
| `ALGORITHM` | `fixed_window`, `sliding_window_counter`, or `token_bucket`. |
| `LIMIT` | For fixed and sliding-window algorithms, the maximum requests per window. For token bucket, the number of tokens replenished per window. |
| `WINDOW_SECONDS` | The window or refill period, in seconds. |
| `KEY_FUNCTION` | Dotted path to the function that returns a client key. |
| `BACKEND` | `memory` or `redis`. |
| `REDIS_URL` | Redis connection URL. Required when `BACKEND` is `redis`. |
| `BURST_CAPACITY` | Maximum tokens in the bucket. Token-bucket only; defaults to `LIMIT`. |
| `FAIL_OPEN` | Whether to allow requests if the backend fails. Defaults to `False`. |
| `REDIS_SOCKET_TIMEOUT` | Redis socket timeout in seconds. Defaults to `1.0`. |
| `REDIS_CONNECT_TIMEOUT` | Redis connection timeout in seconds. Defaults to `1.0`. |

### Choosing a client key

The key function determines which requests share a limit. Common choices include an
authenticated user ID, an API key, or a client IP address.

If Django is behind a reverse proxy, `REMOTE_ADDR` may be the proxy address rather than
the original client's address. Use a key function that reads the client IP from a header
only when your proxy is configured to set and protect that header.

## Use as middleware

Add the middleware to your Django project's `MIDDLEWARE` setting:

```python
MIDDLEWARE = [
    # ...
    "django_ratelatch.integrations.middleware.RateLimitMiddleware",
]
```

The middleware applies the configured algorithm, limit, backend, and key function to
requests handled by the project.

## Use as a view decorator

Use the decorator to limit selected views instead of applying the middleware to every
request:

```python
from django_ratelatch.integrations.decorator import rate_limit


@rate_limit()
def my_view(request):
    ...
```

With no argument, the decorator uses the `RATE_LIMITER` settings.

Pass a rate string to override the limit and window for that view. The algorithm,
backend, and key function still come from `RATE_LIMITER`:

```python
@rate_limit("10/m")
def another_view(request):
    ...
```

Supported time units include seconds (`s`, `sec`), minutes (`m`, `min`), and hours
(`h`, `hr`). A multiplier is supported, for example `"30/150s"`.

Avoid applying both the middleware and decorator to the same request path unless you
intend for both checks to run.

## Use with Django REST Framework

Install the `drf` extra, then add `rest_framework` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
]
```

Configure the rate-limiter throttle as a default DRF throttle:

```python
REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_CLASSES": [
        "django_ratelatch.integrations.drf.RateLimitThrottle",
    ],
}
```

The throttle uses the `RATE_LIMITER` settings and key function described above.
Throttled requests receive HTTP `429` and a `Retry-After` header.

If the middleware and DRF throttle both process the same API request, both checks run.
Choose the integration that fits the endpoints you want to limit.

## Algorithms

- **Fixed window** counts requests in aligned time windows. Counters reset when a new
  window starts.
- **Sliding window counter** estimates usage across a rolling window using counts from
  the current and previous windows. It uses less state than a sliding-window log, but
  the count is an approximation.
- **Token bucket** replenishes tokens at a steady rate and allows requests while tokens
  are available. `BURST_CAPACITY` controls how many requests can be accepted in a burst.

## Storage and backend failures

The in-memory backend is process-local. Its state is not shared between separate worker
processes or servers. Use Redis when those processes must share limits.

When the backend fails, `FAIL_OPEN` controls the integration behavior:

- `False` (default): fail closed. Middleware and the decorator return HTTP `503`; the DRF
  integration raises a `503` API exception.
- `True`: fail open. The request proceeds without a rate-limit decision.

## Supported versions

The test suite runs on supported Python/Django combinations for Python 3.11–3.14 and
Django 5.2, 6.0, and 6.1.

## Development

Clone the repository, then install the development dependencies:

```bash
uv sync --all-extras --dev
```

Run the test suite with:

```bash
uv run pytest
```

Redis integration tests require a Redis server and `RATE_LIMITER_REDIS_URL`. The Redis
middleware integration test is skipped when that environment variable is not set.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
