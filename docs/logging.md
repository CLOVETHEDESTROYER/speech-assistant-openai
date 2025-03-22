# Logging Configuration

This document describes the logging configuration for the Speech Assistant API and provides best practices for logging.

## Overview

The application uses Python's standard logging module with enhanced configuration:

1. **Console logging** for development and debugging
2. **File-based logging** with rotation for production use
3. **Sensitive data filtering** to prevent accidental exposure of credentials
4. **Configurable log levels** via environment variables

## Configuration Settings

The following settings can be configured through environment variables:

| Environment Variable | Description                                           | Default                                              |
| -------------------- | ----------------------------------------------------- | ---------------------------------------------------- |
| `LOG_LEVEL`          | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | INFO                                                 |
| `LOG_DIR`            | Directory for log files                               | logs                                                 |
| `LOG_MAX_SIZE_MB`    | Maximum size in MB before rotating log files          | 10                                                   |
| `LOG_BACKUP_COUNT`   | Number of backup log files to keep                    | 5                                                    |
| `LOG_FORMAT`         | Format string for log messages                        | %(asctime)s - %(name)s - %(levelname)s - %(message)s |

## Log Files

Log files are stored in the directory specified by `LOG_DIR` (default: `logs/`):

- `app.log` - Current log file
- `app.log.1`, `app.log.2`, etc. - Rotated backup log files

The system automatically rotates log files when they reach the size specified by `LOG_MAX_SIZE_MB`.

## Sensitive Data Protection

The logging system includes a filter that automatically redacts sensitive information:

- API keys (OpenAI, Twilio)
- Authentication tokens
- Credentials

When logging request data that might contain sensitive information, use the dedicated utility functions to sanitize the data.

## Best Practices

### Log Levels

- **DEBUG**: Detailed information, typically useful only when diagnosing problems
- **INFO**: Confirmation that things are working as expected
- **WARNING**: An indication that something unexpected happened, but the application is still working
- **ERROR**: Due to a more serious problem, the application has not been able to perform a function
- **CRITICAL**: A serious error, indicating that the application itself may be unable to continue running

### What to Log

1. **DO log**:

   - Application startup and shutdown events
   - Authentication events (success/failure)
   - API call errors and exceptions
   - Rate limiting events
   - Performance metrics

2. **DO NOT log**:
   - Complete request/response bodies (which may contain PII)
   - User passwords or authentication tokens
   - Credit card information or other financial data
   - Personally identifiable information (PII)

### Logging Format

Follow these guidelines for consistent logging:

1. Use consistent terminology in log messages
2. Include relevant context in log messages
3. For errors, include enough information to understand what went wrong
4. When logging exceptions, use `logger.exception()` to include the stack trace

Example:

```python
try:
    # Operation that might fail
    result = process_item(item_id)
except Exception as e:
    logger.exception(f"Failed to process item {item_id}")
    # Handle the exception
```

## Log Analysis

For production deployments, consider integrating with a log management system such as:

- ELK Stack (Elasticsearch, Logstash, Kibana)
- Datadog
- New Relic
- Loggly

These systems provide better visualization, searching, and alerting capabilities based on your logs.
