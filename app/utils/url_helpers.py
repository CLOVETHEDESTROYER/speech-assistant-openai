from urllib.parse import urlparse
import ipaddress
import re


def is_private_host(hostname: str) -> bool:
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        # Not an IP; check common localhost names
        return hostname in {"localhost", "127.0.0.1"}


def clean_and_validate_url(url: str, add_protocol: bool = True, allow_private: bool = False, allowed_domains: list[str] | None = None) -> str:
    """
    Normalize and validate a URL.

    - Enforces https scheme (unless add_protocol is False and scheme present)
    - Validates hostname is present
    - Optionally rejects private/localhost hosts
    - Optionally restricts to an allowlist of domains (exact or subdomains)
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL is required")

    candidate = url.strip()

    # Prepend https if missing scheme
    if add_protocol and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", candidate):
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)

    if parsed.scheme not in {"https"}:  # only https
        raise ValueError("Only https URLs are allowed")

    if not parsed.hostname:
        raise ValueError("URL must include a valid host")

    hostname = parsed.hostname

    if not allow_private and is_private_host(hostname):
        raise ValueError("Private or localhost hosts are not allowed")

    if allowed_domains:
        # allow subdomains of any allowed domain
        def matches(domain: str) -> bool:
            return hostname == domain or hostname.endswith("." + domain)

        if not any(matches(domain) for domain in allowed_domains):
            raise ValueError("Host is not in the allowed domains list")

    # Recompose normalized URL (drop fragments)
    normalized = parsed._replace(fragment="").geturl()
    return normalized
