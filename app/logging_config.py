import logging
import logging.handlers
import os
from app import config


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, "msg") and isinstance(record.msg, str):
            for env_key in ["OPENAI_API_KEY", "TWILIO_AUTH_TOKEN", "SECRET_KEY", "DATA_ENCRYPTION_KEY"]:
                val = os.getenv(env_key)
                if val and val in record.msg:
                    record.msg = record.msg.replace(
                        val, f"[{env_key}_REDACTED]")
        return True


def configure_logging() -> logging.Logger:
    # Get log level from config
    log_level_name = config.LOG_LEVEL.upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Ensure log directory exists
    os.makedirs(config.LOG_DIR, exist_ok=True)

    logging.basicConfig(
        level=log_level,
        format=config.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(),
            logging.handlers.RotatingFileHandler(
                os.path.join(config.LOG_DIR, 'app.log'),
                maxBytes=config.LOG_MAX_SIZE_MB * 1024 * 1024,
                backupCount=config.LOG_BACKUP_COUNT,
                encoding='utf-8'
            )
        ]
    )

    logger = logging.getLogger(__name__)
    logger.addFilter(SensitiveDataFilter())
    return logger
