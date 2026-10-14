// Execute the existing API wrapper with isolated transport doubles. No backend writes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import { NativeFormData, convertFormDataAsync, loadTs } from './nativeRuntime.mjs';

function client(respond, platform = 'web', config = {}) {
  const requests = [];
  const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  const response = (url, options) => respond ? respond(url, options)
    : { ok: true, json: async () => ({ id: 'saved-test-record', analysis_status: 'not_requested' }) };
  const nativeRequests = [];
  class NativeXHR {
    controller = new AbortController();
    aborted = false;
    constructor() { nativeRequests.push(this); }
    open(method, url) { this.method = method; this.url = url; }
    send(body) {
      if (config.sendThrows) throw new Error('Native send failed');
      assert.equal(typeof body.getParts, 'function');
      this.parts = body.getParts(); // The actual RN networking serialization boundary.
      const options = { method: this.method, body, signal: this.controller.signal };
      requests.push({ url: this.url, options, transport: 'xhr' });
      Promise.resolve().then(() => response(this.url, options)).then(async result => {
        this.status = result.status ?? (result.ok === false ? 500 : 200);
        this.headers = result.headers;
        try { this.responseText = JSON.stringify(await result.json()); }
        catch { this.responseText = '<invalid json>'; }
        this.onload?.();
      }, error => { if (error.name === 'AbortError') this.onabort?.(); else this.onerror?.(); });
    }
    abort() { this.aborted = true; this.controller.abort(); this.onabort?.(); }
    getResponseHeader(name) { return this.headers?.get(name) ?? null; }
    setRequestHeader() { assert.fail('Native upload must let the runtime set multipart headers'); }
  }
  const native = loadTs('../src/nativeMultipartUpload.ts', { XMLHttpRequest: NativeXHR });
  runInNewContext(compiled, {
    exports, __DEV__: Boolean(config.logs), console: { info: (...args) => config.logs?.push(args) }, require: (name) => {
      if (name === 'expo-file-system') return { File: config.File || class { exists = true; size = 1234; type = ''; } };
      if (name === './nativeMultipartUpload') return native;
      assert.equal(name, 'react-native'); return { Platform: { OS: platform } };
    },
    process: { env: { EXPO_PUBLIC_API_URL: config.url ?? 'http://test-only' } },
    FormData: platform === 'web' ? FormData : NativeFormData,
    Blob, URL, AbortController, setTimeout: config.setTimeout || setTimeout, clearTimeout, Error, TypeError,
    fetch: async (url, options) => {
      requests.push({ url, options, transport: 'fetch' });
      if (platform !== 'web' && options?.body instanceof NativeFormData) await convertFormDataAsync(options.body);
      if (url === 'fixture-image') return { blob: async () => new Blob(['temporary test bytes'], { type: 'image/png' }) };
      return response(url, options);
    },
  });
  return { api: exports.api, requests, nativeRequests };
}

test('demo access failures ask for sign-in without suggesting browser secrets', async () => {
  for (const status of [401, 403]) {
    const { api } = client(() => ({ ok: false, status }), 'web', { url: 'https://demo.pages.dev/api' });
    await assert.rejects(api.plants(), error => error.code === 'demo_access_denied' && /sign.in/i.test(error.message));
  }
  const redirected = client(() => ({ ok: true, redirected: true }), 'web', { url: 'https://demo.pages.dev/api' });
  await assert.rejects(redirected.api.plants(), error => error.code === 'demo_access_denied');
  const offline = client(() => { throw new TypeError('Failed to fetch'); }, 'web', { url: 'https://demo.pages.dev/api' });
  await assert.rejects(offline.api.plants(), error => /sign.in/i.test(error.message) && !/laptop/i.test(error.message));
});

test('record save/retry calls only records and retains request identity, omitting absent values', async () => {
  const { api, requests } = client();
  const image = { uri: 'fixture-image', fileName: 'fixture.png' };
  const context = { temperature: 25, humidity: 60, soil_type: 'Loamy', soil_condition: 'Normal' };
  const details = { request_id: 'same-request', observed_at: null, tracking_ref: null, notes: null };
  await api.record('plant-a', image, context, details);
  await api.record('plant-a', image, context, details);
  const saves = requests.filter(item => item.options?.method === 'POST');
  assert.equal(saves.length, 2);
  for (const { url, options } of saves) {
    assert.equal(url, 'http://test-only/plants/plant-a/records');
    assert.equal(options.method, 'POST');
    assert.equal(options.body.get('request_id'), 'same-request');
    assert.equal(options.body.get('temperature'), '25');
    for (const absent of ['observed_at', 'tracking_ref', 'notes', 'disease', 'severity', 'confidence']) assert.equal(options.body.has(absent), false);
  }
  assert.equal(requests.some(item => item.url.endsWith('/predict')), false);
});

test('progression query encodes user-entered leaf reference', async () => {
  const { api, requests } = client();
  await api.progression('plant-a', ' Leaf A & B ');
  assert.equal(requests[0].url, 'http://test-only/plants/plant-a/progression?tracking_ref=Leaf%20A%20%26%20B');
});

test('plant creation transmits a stable retry identity', async () => {
  const { api, requests } = client();
  await api.addPlant('Plant A', 'tomato', 'plant-request-001');
  await api.addPlant('Plant A', 'tomato', 'plant-request-001');
  assert.deepEqual(requests.map(r => JSON.parse(r.options.body)), [
    { name:'Plant A', crop_name:'tomato', request_id:'plant-request-001' },
    { name:'Plant A', crop_name:'tomato', request_id:'plant-request-001' },
  ]);
});

test('analysis save sends image, context and stable request identity to observations', async () => {
  const { api, requests } = client();
  const details = { request_id: 'analysis-request', observed_at: '2025-01-01T10:00:00Z', tracking_ref: 'leaf-a', notes: 'field note' };
  await api.scan('plant-a', { uri: 'fixture-image', fileName: 'fixture.png' },
    { temperature: 25, humidity: 60, soil_type: 'Loamy', soil_condition: 'Normal' }, details);
  const save = requests.find(item => item.options?.method === 'POST');
  assert.equal(save.url, 'http://test-only/plants/plant-a/observations');
  for (const [key, value] of Object.entries(details)) assert.equal(save.options.body.get(key), value);
  assert.ok(save.options.body.get('image') instanceof Blob);
  for (const key of ['disease', 'severity', 'confidence', 'prediction_score', 'is_mock']) assert.equal(save.options.body.has(key), false);
});


test('analysis omits missing environment instead of manufacturing values', async () => {
  const { api, requests } = client();
  await api.scan('plant-a', { uri: 'fixture-image' },
    { temperature: null, humidity: null, soil_type: null, soil_condition: null },
    { request_id: 'optional-env', observed_at: '2026-01-01T00:00:00Z', observed_timezone: 'Asia/Kolkata (UTC+05:30)', tracking_ref: null, notes: null });
  const form = requests.find(r => r.options?.method === 'POST').options.body;
  for (const field of ['temperature', 'humidity', 'soil_type', 'soil_condition', 'notes']) assert.equal(form.has(field), false);
  assert.equal(form.get('observed_timezone'), 'Asia/Kolkata (UTC+05:30)');
});

for (const [label, respond, message] of [
  ['network', () => { throw new TypeError('Failed to fetch'); }, /Cannot reach/],
  ['timeout', () => { const error = new Error(); error.name = 'AbortError'; throw error; }, /Refresh history before retrying/],
  ['model', () => ({ ok: false, status: 503, json: async () => ({ detail: 'Prediction service unavailable. No observation was saved.' }) }), /No observation was saved/],
  ['image', () => ({ ok: false, status: 415, json: async () => ({ detail: { is_valid: false, message: 'Unsupported image format' } }) }), /Unsupported image format/],
]) {
  test(`${label} failure rejects analysis instead of creating a Healthy result`, async () => {
    const { api } = client(respond);
    await assert.rejects(api.scan('plant-a', { uri: 'fixture-image' }, {}, { request_id: 'failure-test' }), message);
  });
}

for (const code of ['non_plant_image', 'plant_content_uncertain', 'plant_screening_unavailable']) {
  test(`suitability ${code} preserves the server explanation and code`, async () => {
    const { api } = client(() => ({ ok: false, status: code.endsWith('unavailable') ? 503 : 422,
      json: async () => ({ detail: { code, message: 'Choose a clear tomato leaf photo.' } }) }));
    await assert.rejects(api.checkSuitability({ uri: 'fixture-image' }), error =>
      error.code === code && error.message === 'Choose a clear tomato leaf photo.');
    await assert.rejects(api.scan('p', { uri: 'fixture-image' }, {}, {}), error => error.code === code);
  });
}
test('suitability preview uses its own endpoint without predicting or saving', async () => {
  const { api, requests } = client(() => ({ ok: true, json: async () => ({ outcome: 'plant', message: 'Plant content supported' }) }));
  assert.equal((await api.checkSuitability({ uri: 'fixture-image' })).outcome, 'plant');
  assert.deepEqual(requests.filter(r => r.options?.method === 'POST').map(r => r.url), ['http://test-only/check-plant-suitability']);
});

test('native camera URI uses existing multipart file upload for validation, suitability and analysis',async()=>{
  const {api,requests,nativeRequests}=client(undefined,'android');
  const image={uri:'file:///cache/fresh-camera.jpg',fileName:'fresh-camera.jpg',mimeType:'image/jpeg'};
  await api.validateImage(image);await api.checkSuitability(image);
  await api.scan('plant-a',image,{}, {request_id:'camera-analysis-001'});
  assert.deepEqual(requests.map(r=>r.url),['http://test-only/validate-image','http://test-only/check-plant-suitability',
    'http://test-only/plants/plant-a/observations']);
  for(const {options} of requests) {
    assert.equal(requests[requests.findIndex(r=>r.options===options)].transport,'xhr');
    assert.equal(options.body.get('image').uri,image.uri);
    assert.equal(options.body.get('image').name,image.fileName);
    assert.equal(options.body.get('image').type,'image/jpeg');
    assert.equal(options.headers,undefined); // The runtime supplies the multipart boundary.
  }
  assert.equal(nativeRequests.length,3);
  const nativeFile = nativeRequests[0].parts[0];
  assert.equal(nativeFile.uri,image.uri); assert.equal(nativeFile.name,image.fileName);
  assert.equal(nativeFile.type,image.mimeType);
  assert.match(nativeFile.headers['content-disposition'],/filename="fresh-camera.jpg"/);
  assert.equal(nativeFile.headers['content-type'],'image/jpeg');
  // This is the installed Expo SDK 57 failure reproduced on the exact RN part.
  await assert.rejects(convertFormDataAsync(requests[0].options.body),/Unsupported FormDataPart implementation/);
  assert.equal(requests[2].options.body.get('request_id'),'camera-analysis-001');
});

test('browser camera blob bytes survive the existing validation and analysis upload path',async()=>{
  const blob=new Blob(['captured-jpeg-fixture'],{type:'image/jpeg'});const uri=URL.createObjectURL(blob);
  try {
    const {api,requests}=client((url)=>url===uri?fetch(uri):{ok:true,json:async()=>({id:'saved'})});
    const image={uri,fileName:'camera-photo.jpg',mimeType:'image/jpeg'};
    await api.validateImage(image);await api.scan('plant-a',image,{}, {request_id:'browser-camera-001'});
    for(const {options} of requests.filter(r=>r.options?.method==='POST')) {
      const file=options.body.get('image');assert.equal(await file.text(),'captured-jpeg-fixture');
      assert.equal(file.type,'image/jpeg');assert.equal(file.name,'camera-photo.jpg');
      for(const key of ['disease','confidence','severity'])assert.equal(options.body.has(key),false);
    }
    assert.ok(requests.filter(r=>r.options?.method==='POST').every(r=>r.transport==='fetch'));
  } finally {URL.revokeObjectURL(uri);}
});

for (const url of ['', 'http://localhost:8000', 'http://127.0.0.1:8000', 'http://[::1]:8000', 'http://0.0.0.0:8000', 'not-a-url']) {
  test(`native API configuration fails before upload: ${url || 'unset'}`, async () => {
    const { api, requests } = client(undefined, 'android', { url });
    await assert.rejects(api.validateImage({ uri: 'file:///camera.jpg' }), e => e.code === 'api_configuration' && /EXPO_PUBLIC_API_URL/.test(e.message));
    assert.equal(requests.length, 0);
  });
}

test('native client accepts a configured HTTPS production API URL', async () => {
  const { api, requests } = client(undefined, 'android', {
    url: 'https://api.example.test',
    File: class { exists = true; size = 123; type = 'image/jpeg'; },
  });
  await api.validateImage({ uri: 'content://media/images/production-test' });
  assert.equal(requests[0].url, 'https://api.example.test/validate-image');
  assert.equal(requests[0].transport, 'xhr');
});

test('web loopback and explicitly configured native LAN backend remain usable', async () => {
  for (const [platform, url] of [['web', 'http://localhost:8000/'], ['android', 'http://192.168.1.50:8000/']]) {
    const { api, requests } = client(undefined, platform, { url });
    await api.health(); assert.equal(requests[0].url, url + 'health');
  }
});

for (const [label, file, code] of [
  ['missing', { exists: false, size: 1 }, 'photo_unavailable'],
  ['empty', { exists: true, size: 0 }, 'photo_unavailable'],
  ['oversize', { exists: true, size: 10 * 1024 * 1024 + 1 }, 'upload_too_large'],
]) test(`native ${label} photo fails locally before any HTTP upload`, async () => {
  const { api, requests } = client(undefined, 'android', { File: class { constructor() { Object.assign(this, file); } } });
  await assert.rejects(api.checkSuitability({ uri: 'file:///cache/camera.jpg', fileSize: 123 }), e => e.code === code);
  assert.equal(requests.length, 0);
});

test('native file availability is rechecked after a preview and before save', async () => {
  let exists = true;
  const { api, requests } = client(undefined, 'android', { File: class { get exists() { return exists; } size = 123; } });
  const photo = { uri: 'file:///cache/camera.jpg' };
  await api.validateImage(photo); exists = false;
  await assert.rejects(api.scan('p', photo, {}, {}), e => e.code === 'photo_unavailable');
  assert.equal(requests.length, 1);
});

for (const uri of ['file:///cache/camera.png', 'content://media/images/12']) test(`native filename and MIME fallback preserve ${uri}`, async () => {
  const { api, requests, nativeRequests } = client(undefined, 'android', { File: class { exists = true; size = 123; type = 'image/png'; } });
  await api.predict({ uri });
  const file = requests[0].options.body.get('image');
  assert.equal(file.uri, uri); assert.equal(file.type, 'image/png'); assert.equal(file.name, 'leaf.png');
  assert.equal(requests[0].options.headers, undefined);
  assert.equal(requests[0].transport,'xhr');
  assert.equal(nativeRequests[0].parts[0].uri,uri);
});

test('native upload failure differs from a backend health connection failure', async () => {
  const { api } = client(() => { throw new TypeError('Network request failed'); }, 'android');
  await assert.rejects(api.validateImage({ uri: 'file:///cache/camera.jpg' }), e => e.code === 'upload_failed' && /receipt is unknown/.test(e.message));
  await assert.rejects(api.health(), e => e.code === 'backend_unreachable' && /changed laptop IP/.test(e.message));
});

test('actual abort timer distinguishes check timeout from an uncertain save', async () => {
  const { api } = client((url, options) => new Promise((resolve, reject) => {
    options.signal.addEventListener('abort', () => { const error = new Error(); error.name = 'AbortError'; reject(error); });
  }), 'android', { setTimeout: (callback, ms) => { assert.equal(ms, 30000); return setTimeout(callback, 1); } });
  await assert.rejects(api.checkSuitability({ uri: 'file:///cache/camera.jpg' }), e => e.code === 'request_timeout' && !/may have completed/.test(e.message));
  await assert.rejects(api.scan('p', { uri: 'file:///cache/camera.jpg' }, {}, {}), /save may have completed/);
});

for (const code of ['unsupported_crop', 'inference_failed', 'model_unavailable']) test(`server ${code} reaches the user with its reason`, async () => {
  const { api } = client(() => ({ ok: false, status: 503, json: async () => ({ detail: { code, message: 'Specific backend explanation' } }) }), 'android');
  await assert.rejects(api.predict({ uri: 'file:///cache/camera.jpg' }), e => e.code === code && /Specific backend explanation/.test(e.message));
});

test('non-JSON backend failure retains HTTP status; malformed success is not a prediction', async () => {
  for (const ok of [false, true]) {
    const { api } = client(() => ({ ok, status: ok ? 200 : 502, json: async () => { throw new SyntaxError('HTML'); } }), 'android');
    await assert.rejects(api.predict({ uri: 'file:///cache/camera.jpg' }), e => ok ? e.code === 'invalid_response' : /HTTP 502/.test(e.message));
  }
});

test('development diagnostics include response reference without photo URI, plant ID or notes', async () => {
  const logs = [];
  const { api } = client(() => ({ ok: true, status: 201, headers: new Headers({ 'x-agrisense-request-id': 'safe-reference' }), json: async () => ({ id: 'saved' }) }), 'android', { logs });
  await api.scan('private-plant-id', { uri: 'file:///private-camera.jpg' }, {}, { notes: 'private notes', request_id: 'private-key' });
  const output = JSON.stringify(logs);
  assert.match(output, /safe-reference/); assert.match(output, /\/plants\/:id\/observations/);
  for (const value of ['private-plant-id', 'private-camera', 'private notes', 'private-key']) assert.ok(!output.includes(value));
});
