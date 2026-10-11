"""Bound uploads before multipart spooling and reject unapproved browser writes.

Origin checks protect browser use; they are not authentication or network access control.
"""
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from .image_validation import MAX_IMAGE_BYTES

MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + 128 * 1024


class LocalRequestBoundary:
    def __init__(self, app, allowed_origins):
        self.app = app
        self.allowed_origins = set(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        async def secured_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = [(k, v) for k, v in message.get('headers', []) if k.lower() != b'cache-control']
                message['headers'] += [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')]
            await send(message)
        if scope['method'] in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = headers.get(b'origin')
            if origin is not None and origin.decode('latin-1') not in self.allowed_origins:
                return await JSONResponse({'detail': 'Browser origin is not allowed.'}, status_code=403)(scope, receive, secured_send)
        length = headers.get(b'content-length')
        if length is not None:
            try:
                length = int(length)
                if length < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse({'detail': 'Invalid Content-Length.'}, status_code=400)(scope, receive, secured_send)
            if length > MAX_REQUEST_BYTES:
                return await JSONResponse({'detail': 'Request exceeds the upload limit.'}, status_code=413)(scope, receive, secured_send)
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message['type'] == 'http.request':
                received += len(message.get('body', b''))
                if received > MAX_REQUEST_BYTES:
                    raise HTTPException(413, 'Request exceeds the upload limit.')
            return message
        await self.app(scope, bounded_receive, secured_send)
