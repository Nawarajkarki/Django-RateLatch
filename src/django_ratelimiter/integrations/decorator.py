import re
from functools import wraps
import inspect
from asgiref.sync import sync_to_async


from django.conf import settings
from django.http import HttpResponse
from django.utils.module_loading import import_string

from django_ratelimiter.core.limiter import build_limiter
from django_ratelimiter.backends.factory import build_backend
from django.core.exceptions import ImproperlyConfigured
from django_ratelimiter.exceptions import RateLimiterBackendError

"""
Allow devs to config per view limiter decorators as 
rate_limit(10/min) OR rate_limit(10/sec)
"""

multiplier_map = {
    's': 1, 'sec' : 1, "secs":1, "second":1, "seconds":1,
    "m":60, "min":60, "mins":60, "minute":60, "minutes":60,
    "h":3600, "hr": 3600, "hrs":3600, "hour":3600, "hours":3600
}

def parse_rate_string(rate_str):
    """
    Parses strings like '10/m', '10/30s', '5/5min', '100/2h' as 
    10 request per minute
    10 request per 30 seconds. ...
    """
    if not isinstance(rate_str, str):
        raise TypeError("rate limit must be a string, such as '10/s'")
    
    pattern = r"^(?P<limit>\d+)\s*/\s*(?P<multiplier>\d*)(?P<unit>[a-zA-Z]+)$"
    
    match = re.match(pattern, rate_str.strip().lower())
    
    if not match:
        raise ValueError(f"Invalid rate limit format: '{rate_str}'. Use format like '10/m' or '10/30s'")

    data = match.groupdict()
    limit = int(data["limit"])
    multiplier_val = int(data["multiplier"]) if data["multiplier"] else 1
    unit = data["unit"]

    multiplier_map = {
        's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
        'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
        'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
    }

    if unit not in multiplier_map:
        raise ValueError(f"Unknown time unit: '{unit}'")

    window_seconds = multiplier_val * multiplier_map[unit]

    # result = {"limit": limit, "window_seconds": window_seconds}

    if limit <= 0 or multiplier_val <= 0:
            raise ValueError("rate limit and duration must be greater than zero")
        
        
    return limit, window_seconds




def rate_limit(rate_string = None):
    # self. get_response = get_response
            
    config = settings.RATE_LIMITER.copy()

    fail_open = config.get("FAIL_OPEN", False)
    if not isinstance(fail_open, bool):
        raise ImproperlyConfigured("RATE_LIMITER['FAIL_OPEN'] must be a boolean.")

    if rate_string is not None:
        limit, window_seconds = parse_rate_string(rate_string)
        
        config['LIMIT'] = limit
        config["WINDOW_SECONDS"] = window_seconds

    key_function = import_string(config["KEY_FUNCTION"])
    
    backend = build_backend(config=config)
    limiter = build_limiter(config=config, backend=backend)
    
    async_key_function = sync_to_async(key_function, thread_sensitive=True)
    async_limiter_check = sync_to_async(limiter.check, thread_sensitive=False)
    
    
    
    def backend_failure_response():
        return HttpResponse(
            "Rate limiter temporarily unavailable",
            status=503,
        )
                
                
    def decorator(view_func):
        view_scope = f"{view_func.__module__}.{view_func.__qualname__}"
                
        def make_rejection_response(decision):
            response = HttpResponse("Too many requests", status=429)
            response["Retry-After"] = str(decision["retry_after"])
            return response

        if inspect.iscoroutinefunction(view_func):

            @wraps(view_func)
            async def _wrapped_async_view(request, *args, **kwargs):
                client_key = await async_key_function(request)
                scoped_key = f"{view_scope}:{client_key}"
                
                try:
                    decision = await async_limiter_check(key=scoped_key)
                except RateLimiterBackendError:
                    if fail_open:
                        return await view_func(request, *args, **kwargs)
                    return backend_failure_response()

                if not decision["allowed"]:
                    return make_rejection_response(decision)

                return await view_func(request, *args, **kwargs)

            return _wrapped_async_view

        @wraps(view_func)
        def _wrapped_sync_view(request, *args, **kwargs):
            client_key = key_function(request)
            scoped_key = f"{view_scope}:{client_key}"

            try:
                decision = limiter.check(key=scoped_key)
            except RateLimiterBackendError:
                if fail_open:
                    return view_func(request, *args, **kwargs)
                return backend_failure_response()
            
            if not decision["allowed"]:
                return make_rejection_response(decision)

            return view_func(request, *args, **kwargs)
        

        return _wrapped_sync_view
    return decorator

