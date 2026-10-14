import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { onRequest } from '../functions/api/[[path]].js';
import { validatePagesApiUrl } from '../scripts/build-pages.mjs';

const env = { AGRISENSE_BACKEND_ORIGIN: 'https://demo.up.railway.app', AGRISENSE_FRONTEND_ORIGIN: 'https://demo.pages.dev' };
const headers = { 'Cf-Access-Jwt-Assertion': 'synthetic-jwt-for-forwarding-test' };

test('Pages build rejects localhost, HTTP, credentials and malformed API paths', () => {
  assert.equal(validatePagesApiUrl('https://demo.pages.dev/api').origin, env.AGRISENSE_FRONTEND_ORIGIN);
  for (const value of [undefined, '', 'http://demo.pages.dev/api', 'https://localhost/api',
    'https://user:secret@demo.pages.dev/api', 'https://demo.pages.dev', 'https://demo.pages.dev/api?secret=test']) {
    assert.throws(() => validatePagesApiUrl(value));
  }
});

test('Pages configuration exports an SPA with camera permission and API function routing', () => {
  const root = new URL('../', import.meta.url);
  assert.equal(JSON.parse(readFileSync(new URL('app.json', root))).expo.web.output, 'single');
  assert.deepEqual(JSON.parse(readFileSync(new URL('public/_routes.json', root))).include, ['/api', '/api/*']);
  assert.match(readFileSync(new URL('public/_headers', root), 'utf8'), /camera=\(self\)/);
});

test('proxy refuses missing identity, preview origin and cross-origin mutations', async () => {
  assert.equal((await onRequest({ request: new Request('https://demo.pages.dev/api/plants'), env })).status, 401);
  assert.equal((await onRequest({ request: new Request('https://preview.demo.pages.dev/api/plants', { headers }), env })).status, 503);
  assert.equal((await onRequest({ request: new Request('https://demo.pages.dev/api/plants', { method: 'POST', headers }), env })).status, 403);
  assert.equal((await onRequest({ request: new Request('https://demo.pages.dev/api/plants', { method: 'DELETE', headers }), env })).status, 405);
});

test('multipart proxy preserves file bytes and sends only selected headers', async t => {
  const form = new FormData();
  form.append('image', new Blob(['synthetic-image'], { type: 'image/jpeg' }), 'fixture.jpg');
  form.append('notes', 'synthetic note');
  const request = new Request('https://demo.pages.dev/api/plants/p/records', { method: 'POST', body: form,
    headers: { ...headers, Origin: env.AGRISENSE_FRONTEND_ORIGIN, Cookie: 'private-cookie', Authorization: 'untrusted', 'X-Forwarded-Host': 'attacker' } });
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(String(url), 'https://demo.up.railway.app/plants/p/records');
    assert.equal(options.redirect, 'manual');
    assert.equal(options.headers.get('cf-access-jwt-assertion'), headers['Cf-Access-Jwt-Assertion']);
    for (const name of ['cookie', 'authorization', 'x-forwarded-host']) assert.equal(options.headers.get(name), null);
    const forwarded = await new Request(url, options).formData();
    assert.equal(await forwarded.get('image').text(), 'synthetic-image');
    assert.equal(forwarded.get('notes'), 'synthetic note');
    return Response.json({ id: 'test-only' }, { status: 201, headers: { 'set-cookie': 'unexpected', 'cache-control': 'public' } });
  });
  const result = await onRequest({ request, env });
  assert.equal(result.status, 201);
  assert.equal(result.headers.get('cache-control'), 'no-store');
  assert.equal(result.headers.get('set-cookie'), null);
});

test('proxy serves private photos without caching and never changes the upstream host', async t => {
  t.mock.method(globalThis, 'fetch', async url => {
    assert.equal(url.origin, env.AGRISENSE_BACKEND_ORIGIN);
    return new Response('synthetic-photo', { headers: { 'content-type': 'image/jpeg' } });
  });
  for (const path of ['/api/uploads/photo.jpg', '/api//attacker.invalid/path']) {
    const result = await onRequest({ request: new Request(env.AGRISENSE_FRONTEND_ORIGIN + path, { headers }), env });
    assert.equal(await result.text(), 'synthetic-photo');
    assert.equal(result.headers.get('cache-control'), 'no-store');
  }
});

test('upstream redirects and network failures become sanitized failures', async t => {
  const request = new Request('https://demo.pages.dev/api/plants', { headers });
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => Response.redirect('https://untrusted.invalid'));
  assert.equal((await onRequest({ request, env })).status, 502);
  fetchMock.mock.mockImplementation(async () => { throw new Error('private upstream details'); });
  const response = await onRequest({ request, env });
  assert.equal(response.status, 502);
  assert.doesNotMatch(await response.text(), /private upstream/);
});
