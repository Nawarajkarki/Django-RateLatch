from django.conf import settings
from django.http import HttpResponse
from django.utils.module_loading import import_string

from django_ratelimiter.core.limiter import build_limiter
from django_ratelimiter.backends.factory import build_backend
from django.core.exceptions import ImproperlyConfigured
from django_ratelimiter.exceptions import RateLimiterBackendError

class RateLimitMiddleware:
    
    def __init__(self, get_response):
        
                
        self. get_response = get_response
        
        config = settings.RATE_LIMITER
        
        self.fail_open = config.get("FAIL_OPEN", False)
        if not isinstance(self.fail_open, bool):
            raise ImproperlyConfigured("RATE_LIMITER['FAIL_OPEN'] must be a boolean.")
        
        key_function = import_string(config["KEY_FUNCTION"])
        
        backend = build_backend(config)
        self.key_function = key_function
        self.limiter = build_limiter(config=config, backend=backend)

        
        
    

    def __call__(self, request):
        key = self.key_function(request)

        try:
            decision = self.limiter.check(key)
        except RateLimiterBackendError:
            if self.fail_open:
                return self.get_response(request)

            return HttpResponse(
                "Rate limiter temporarily unavailable",
                status=503,
            )
        
        if not decision["allowed"]:
            response = HttpResponse("Too many requests", status=429)
            response["Retry-After"] = str(decision["retry_after"])
            return response

        return self.get_response(request)
        