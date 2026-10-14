"""Correlated diagnostics without photos, filenames, record IDs or exception text."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from time import monotonic
from uuid import uuid4

logger = logging.getLogger('uvicorn.error')
request_tag = ContextVar('request_tag', default='startup')


def event(stage, **fields):
    # Callers supply only fixed labels, numeric measurements and error class names.
    logger.info('AgriSense request=%s stage=%s %s', request_tag.get(), stage,
                ' '.join(f'{key}={value}' for key, value in fields.items()))


@contextmanager
def stage(name):
    start = monotonic()
    event(name, state='started')
    try:
        yield
    except Exception as error:
        event(name, state='failed', error_type=type(error).__name__,
              duration_ms=round((monotonic() - start) * 1000))
        raise
    else:
        event(name, state='completed', duration_ms=round((monotonic() - start) * 1000))


class RequestDiagnostics:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        token = request_tag.set(uuid4().hex[:12])
        event('request', state='received')

        async def report(message):
            if message['type'] == 'http.response.start':
                event('response', status=message['status'])
                message['headers'] = [*message.get('headers', []),
                                      (b'x-agrisense-request-id', request_tag.get().encode())]
            await send(message)

        try:
            await self.app(scope, receive, report)
        finally:
            request_tag.reset(token)
