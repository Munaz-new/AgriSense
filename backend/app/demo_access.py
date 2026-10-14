"""Cloudflare Access identity boundary for one shared, invited demo journal."""
import os
import re
from threading import Lock

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse


class AccessVerifier:
    def __init__(self):
        import jwt
        self.issuer = os.getenv('AGRISENSE_ACCESS_ISSUER', '')
        self.audience = os.getenv('AGRISENSE_ACCESS_AUD', '')
        self.emails = {email.strip().lower() for email in
                       os.getenv('AGRISENSE_DEMO_EMAILS', '').split(',') if email.strip()}
        if (not re.fullmatch(r'https://[a-z0-9-]+\.cloudflareaccess\.com', self.issuer)
                or not self.audience or not self.emails or '*' in self.emails):
            raise RuntimeError('Production requires AGRISENSE_ACCESS_ISSUER, AGRISENSE_ACCESS_AUD and explicit AGRISENSE_DEMO_EMAILS.')
        self.keys = jwt.PyJWKClient(self.issuer + '/cdn-cgi/access/certs', lifespan=300, timeout=5)
        self.lock = Lock()

    def verify(self, token):
        import jwt
        # Serialize cache refreshes. Never choose a key URL from untrusted claims.
        with self.lock:
            key = self.keys.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['RS256'], issuer=self.issuer,
                            audience=self.audience,
                            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'email']})
        if (not isinstance(claims['email'], str)
                or claims['email'].lower() not in self.emails or not claims['sub']):
            raise ValueError('Identity is not invited.')
        return claims['sub']


class DemoAccessBoundary:
    def __init__(self, app, verifier):
        self.app, self.verifier = app, verifier

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        # Railway cannot attach identity to readiness probes. No journal data here.
        if scope['method'] == 'GET' and scope['path'] == '/ready':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        token = headers.get(b'cf-access-jwt-assertion', b'')
        try:
            if not token or len(token) > 16384:
                raise ValueError('Missing token.')
            await run_in_threadpool(self.verifier.verify, token.decode('ascii'))
        except Exception:
            return await JSONResponse(
                {'detail': 'Demo sign-in required. Reload the page to sign in again.'},
                status_code=401, headers={'Cache-Control': 'no-store'},
            )(scope, receive, send)
        await self.app(scope, receive, send)
