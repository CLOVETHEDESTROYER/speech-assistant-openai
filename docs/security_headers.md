# Security Headers

This document provides detailed information about the security headers implemented in the Speech Assistant API and how to configure them.

## Overview

Security headers are HTTP response headers that, when set, can enhance the security of your web application. They provide instructions to browsers on how to handle your site's content, helping to mitigate common web vulnerabilities like Cross-Site Scripting (XSS), clickjacking, and other code injection attacks.

## Implemented Security Headers

The Speech Assistant API implements the following security headers:

### Content-Security-Policy (CSP)

Content Security Policy is an added layer of security that helps mitigate XSS attacks by allowing you to specify which domains the browser should consider to be valid sources of executable scripts.

Default value:

```
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' wss: https:;
```

This default configuration:

- Restricts scripts, styles, and images to be loaded only from the same origin
- Allows WebSocket connections (needed for real-time audio streaming)
- Allows data: URIs for images (needed for some UI elements)

### X-XSS-Protection

This header enables the browser's built-in Cross-Site Scripting (XSS) filter.

Default value: `1; mode=block`

This setting enables the XSS filter and tells the browser to block the page if an attack is detected, rather than sanitizing the page.

### X-Content-Type-Options

This header prevents MIME type sniffing, which can lead to security vulnerabilities where the browser tries to guess and execute file types.

Default value: `nosniff`

This forces browsers to use the declared content-type of resources, preventing MIME type sniffing.

### X-Frame-Options

This header helps prevent clickjacking attacks by controlling whether a page can be embedded in frames.

Default value: `DENY`

This setting prevents the page from being displayed in a frame, regardless of the site attempting to do so.

### Strict-Transport-Security (HSTS)

HTTP Strict Transport Security (HSTS) tells browsers to only access the application over HTTPS, preventing protocol downgrade attacks and cookie hijacking.

Default value: `max-age=31536000; includeSubDomains`

This configures browsers to enforce HTTPS for one year (31536000 seconds) and includes all subdomains.

### Permissions-Policy

This header allows a site to control which features and APIs can be used in the browser.

Default value:

```
accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(self), payment=(), usb=()
```

This default configuration:

- Disables most sensors and device access
- Allows microphone access only from the same origin (needed for audio interaction)
- Disables payment and USB access

### Referrer-Policy

This header controls how much referrer information is included with requests.

Default value: `strict-origin-when-cross-origin`

This sends the origin, path, and query string when performing a same-origin request, but only sends the origin when the protocol security level stays the same while on a different origin.

### Cache-Control

This header directs browsers on how to cache resources.

Default value: `no-store, max-age=0`

This prevents browsers from caching potentially sensitive information.

## Configuration

All security headers are configurable via environment variables:

| Environment Variable      | Description                                    | Default Value |
| ------------------------- | ---------------------------------------------- | ------------- |
| `ENABLE_SECURITY_HEADERS` | Enable/disable all security headers            | `true`        |
| `CONTENT_SECURITY_POLICY` | Content Security Policy directives             | (See above)   |
| `ENABLE_HSTS`             | Enable HTTP Strict Transport Security          | `true`        |
| `HSTS_MAX_AGE`            | HSTS max age in seconds                        | `31536000`    |
| `XSS_PROTECTION`          | Enable X-XSS-Protection header                 | `true`        |
| `CONTENT_TYPE_OPTIONS`    | Enable X-Content-Type-Options header           | `true`        |
| `FRAME_OPTIONS`           | X-Frame-Options value (DENY, SAMEORIGIN, etc.) | `DENY`        |
| `PERMISSIONS_POLICY`      | Permissions-Policy directives                  | (See above)   |
| `REFERRER_POLICY`         | Referrer-Policy value                          | (See above)   |
| `CACHE_CONTROL`           | Cache-Control value                            | (See above)   |

## Customizing Security Headers

You may need to customize the security headers for your specific deployment scenario. For example, if you're integrating with third-party services, you might need to adjust the Content Security Policy to allow loading resources from those domains.

Example of a more permissive CSP for development:

```
CONTENT_SECURITY_POLICY="default-src 'self' https://api.example.com; script-src 'self' 'unsafe-inline' https://cdn.example.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss: https:;"
```

## Testing Security Headers

You can use online tools like [Security Headers](https://securityheaders.com/) or [Mozilla Observatory](https://observatory.mozilla.org/) to test your deployed application and verify that your security headers are working correctly.

You can also use the provided test suite:

```bash
pytest tests/unit/test_security_headers.py -v
```
