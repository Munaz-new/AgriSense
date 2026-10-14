// Access supplies the user's signed JWT. Railway verifies it independently.
// Only these server-side settings exist here; no service secret goes to Expo.
export async function onRequest({ request, env }) {
  const fail = (status, detail) => Response.json({ detail }, {
    status, headers: { 'Cache-Control': 'no-store' },
  });
  let upstream;
  const incoming = new URL(request.url);
  try {
    upstream = new URL(env.AGRISENSE_BACKEND_ORIGIN);
    const frontend = new URL(env.AGRISENSE_FRONTEND_ORIGIN);
    if (upstream.protocol !== 'https:' || upstream.origin !== env.AGRISENSE_BACKEND_ORIGIN ||
        frontend.protocol !== 'https:' || frontend.origin !== env.AGRISENSE_FRONTEND_ORIGIN ||
        incoming.origin !== frontend.origin || upstream.origin === frontend.origin) {
      return fail(503, 'Demo deployment configuration is incomplete.');
    }
  } catch { return fail(503, 'Demo deployment configuration is incomplete.'); }
  const token = request.headers.get('Cf-Access-Jwt-Assertion');
  if (!token || token.length > 16384) return fail(401, 'Demo sign-in required. Reload the page to sign in again.');
  if (!['GET', 'HEAD', 'POST', 'PATCH'].includes(request.method)) return fail(405, 'Method not allowed.');
  if (['POST', 'PATCH'].includes(request.method) && request.headers.get('Origin') !== incoming.origin) {
    return fail(403, 'Browser origin is not allowed.');
  }
  // Assign the pathname, never resolve an untrusted path as a URL (open proxy).
  upstream.pathname = incoming.pathname.replace(/^\/api(?=\/|$)/, '') || '/';
  upstream.search = incoming.search;
  const headers = new Headers({ 'Cf-Access-Jwt-Assertion': token });
  for (const name of ['Content-Type', 'Origin', 'Accept']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const response = await fetch(upstream, {
      method: request.method, headers,
      body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
      redirect: 'manual', signal: AbortSignal.timeout(35000),
      // Streaming bodies are supported by Workers; Node uses this for tests.
      duplex: 'half',
    });
    // Never forward an origin redirect with an identity token or private hostname.
    if (response.status >= 300 && response.status < 400) return fail(502, 'Unexpected API redirect.');
    const responseHeaders = new Headers({
      'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'",
    });
    for (const name of ['Content-Type', 'X-Agrisense-Request-Id']) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    return new Response(response.body, { status: response.status, headers: responseHeaders });
  } catch { return fail(502, 'Demo API is unavailable. Check history before retrying a save.'); }
}
