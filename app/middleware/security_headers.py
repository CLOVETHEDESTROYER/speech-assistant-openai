from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Callable, Dict


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to every response.

    This helps protect against various attacks like XSS, clickjacking,
    MIME type sniffing, etc.
    """

    def __init__(
        self,
        app: ASGIApp,
        content_security_policy: str = None,
        enable_hsts: bool = True,
        hsts_max_age: int = 31536000,  # 1 year
        include_subdomains: bool = True,
        xss_protection: bool = True,
        content_type_options: bool = True,
        frame_options: str = "DENY",
        permissions_policy: str = None,
        referrer_policy: str = "strict-origin-when-cross-origin",
        cache_control: str = None,
    ):
        super().__init__(app)
        self.content_security_policy = content_security_policy
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.include_subdomains = include_subdomains
        self.xss_protection = xss_protection
        self.content_type_options = content_type_options
        self.frame_options = frame_options
        self.permissions_policy = permissions_policy
        self.referrer_policy = referrer_policy
        self.cache_control = cache_control

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # X-XSS-Protection header
        if self.xss_protection:
            response.headers["X-XSS-Protection"] = "1; mode=block"

        # X-Content-Type-Options header
        if self.content_type_options:
            response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options header
        if self.frame_options:
            response.headers["X-Frame-Options"] = self.frame_options

        # Content-Security-Policy header
        if self.content_security_policy:
            response.headers["Content-Security-Policy"] = self.content_security_policy

        # Strict-Transport-Security header (HSTS)
        if self.enable_hsts:
            hsts_value = f"max-age={self.hsts_max_age}"
            if self.include_subdomains:
                hsts_value += "; includeSubDomains"
            response.headers["Strict-Transport-Security"] = hsts_value

        # Permissions-Policy header
        if self.permissions_policy:
            response.headers["Permissions-Policy"] = self.permissions_policy

        # Referrer-Policy header
        if self.referrer_policy:
            response.headers["Referrer-Policy"] = self.referrer_policy

        # Cache-Control header
        if self.cache_control:
            response.headers["Cache-Control"] = self.cache_control

        return response


def add_security_headers(
    app: FastAPI,
    content_security_policy: str = None,
    enable_hsts: bool = True,
    xss_protection: bool = True,
    content_type_options: bool = True,
    frame_options: str = "DENY",
    permissions_policy: str = None,
    referrer_policy: str = "strict-origin-when-cross-origin",
    cache_control: str = None,
):
    """
    Add security headers middleware to a FastAPI application.

    Args:
        app: FastAPI application
        content_security_policy: Content Security Policy string
        enable_hsts: Enable HTTP Strict Transport Security
        xss_protection: Enable X-XSS-Protection
        content_type_options: Enable X-Content-Type-Options
        frame_options: X-Frame-Options value (DENY, SAMEORIGIN, ALLOW-FROM)
        permissions_policy: Permissions Policy string
        referrer_policy: Referrer Policy value
        cache_control: Cache Control value
    """
    app.add_middleware(
        SecurityHeadersMiddleware,
        content_security_policy=content_security_policy,
        enable_hsts=enable_hsts,
        xss_protection=xss_protection,
        content_type_options=content_type_options,
        frame_options=frame_options,
        permissions_policy=permissions_policy,
        referrer_policy=referrer_policy,
        cache_control=cache_control,
    )
