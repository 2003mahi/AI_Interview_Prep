"""Rate limiting and security headers middleware.

Protects against:
- Brute-force attacks on auth endpoints
- Denial-of-Service (DoS) and API abuse
- Clickjacking and MIME sniffing via standard security headers
"""

import re
import time
from collections import defaultdict
from typing import Dict, List, Tuple
from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from ..config import settings
from ..logger import logger


class SecurityRateLimitMiddleware(BaseHTTPMiddleware):
    request_history: Dict[str, List[float]] = defaultdict(list)

    def __init__(self, app, enabled: bool = True):
        super().__init__(app)
        self.enabled = enabled
        self._last_cleanup = time.time()

    @classmethod
    def reset_limits(cls):
        """Reset all rate limit tracking buckets (useful for test isolation)."""
        cls.request_history.clear()

    def _get_client_ip(self, request: Request) -> str:
        direct_ip = request.client.host if request.client else "127.0.0.1"
        # Only trust X-Forwarded-For if caller is a configured trusted proxy
        if direct_ip in getattr(settings, "trusted_proxies", ["127.0.0.1", "::1"]):
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                candidate = forwarded.split(",")[0].strip()
                if re.match(r"^[0-9a-fA-F:.]+$", candidate):
                    return candidate
        return direct_ip

    def _get_rate_limit(self, path: str) -> Tuple[int, int]:
        """Returns (max_requests, window_seconds) based on endpoint sensitivity."""
        if path.startswith("/api/v1/auth/login") or path.startswith("/api/v1/auth/register"):
            return 15, 60  # Strict limit for authentication endpoints: 15 req/min
        elif path.startswith("/api/v1/documents/upload") or path.startswith("/api/v1/documents/notes"):
            return 30, 60  # Ingestion upload limit: 30 req/min
        elif path.startswith("/api/v1/interview/evaluate") or path.startswith("/api/v1/readiness/analyze"):
            return 45, 60  # AI evaluation limit: 45 req/min
        return 200, 60  # General default API rate limit: 200 req/min

    def _cleanup_old_entries(self, now: float):
        if now - self._last_cleanup > 300:  # Clean every 5 minutes
            cutoff = now - 120
            keys_to_delete = []
            for ip, timestamps in self.request_history.items():
                active = [t for t in timestamps if t > cutoff]
                if active:
                    self.request_history[ip] = active
                else:
                    keys_to_delete.append(ip)
            for k in keys_to_delete:
                del self.request_history[k]
            self._last_cleanup = now

    async def dispatch(self, request: Request, call_next) -> Response:
        now = time.time()
        self._cleanup_old_entries(now)

        path = request.url.path

        # Bypass rate limit for health checks or if disabled
        if self.enabled and path not in ("/health", "/docs", "/openapi.json"):
            client_ip = self._get_client_ip(request)
            max_requests, window = self._get_rate_limit(path)
            bucket_key = f"{client_ip}:{path.split('/')[3] if len(path.split('/')) > 3 else 'root'}"

            history = self.request_history[bucket_key]
            # Keep only timestamps within sliding window
            history = [t for t in history if now - t < window]
            self.request_history[bucket_key] = history

            if len(history) >= max_requests:
                retry_after = int(window - (now - history[0])) if history else window
                logger.warning(
                    f"Rate limit exceeded: IP {client_ip} exceeded limit ({max_requests}/{window}s) on {path}"
                )
                response = JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "Too Many Requests",
                        "detail": f"Rate limit exceeded. Maximum {max_requests} requests per {window} seconds. Please wait {max(1, retry_after)}s before retrying.",
                    },
                    headers={"Retry-After": str(max(1, retry_after))},
                )
                self._add_security_headers(response)
                return response

            history.append(now)

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(f"Unhandled exception during request processing [{path}]: {str(exc)}", exc_info=True)
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal Server Error",
                    "detail": "An unexpected error occurred. The incident has been logged for investigation.",
                },
            )

        self._add_security_headers(response)
        return response

    def _add_security_headers(self, response: Response):
        """Append essential OWASP defense-in-depth headers."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
