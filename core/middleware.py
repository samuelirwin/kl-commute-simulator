"""
Request logging middleware — logs every incoming request with method, path, and response time.
"""
import logging
import time

logger = logging.getLogger("core")


class RequestLoggingMiddleware:
    """Logs HTTP method, path, status code, and response time for each request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000

        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.get_full_path(),
            response.status_code,
            duration_ms,
        )
        return response
