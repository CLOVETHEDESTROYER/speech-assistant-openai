import logging
import logging.handlers
import os
from app import config


class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            if 'OPENAI_API_KEY' in record.msg and os.getenv('OPENAI_API_KEY'):
                record.msg = record.msg.replace(
                    os.getenv('OPENAI_API_KEY'), '[OPENAI_API_KEY_REDACTED]')
            if 'TWILIO_AUTH_TOKEN' in record.msg and os.getenv('TWILIO_AUTH_TOKEN'):
                record.msg = record.msg.replace(
                    os.getenv('TWILIO_AUTH_TOKEN'), '[TWILIO_AUTH_TOKEN_REDACTED]')
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


