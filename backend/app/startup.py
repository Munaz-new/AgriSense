"""Operator diagnostics: stage names and durations, never configuration or exception text."""
from contextlib import contextmanager
import logging
from time import monotonic

logger = logging.getLogger('uvicorn.error')


@contextmanager
def startup_stage(name):
    started = monotonic()
    logger.info('AgriSense startup stage=%s state=started', name)
    try:
        yield
    except Exception as error:
        logger.error('AgriSense startup stage=%s state=failed duration_seconds=%.3f error_type=%s',
                     name, monotonic() - started, type(error).__name__)
        raise
    else:
        logger.info('AgriSense startup stage=%s state=completed duration_seconds=%.3f',
                    name, monotonic() - started)
