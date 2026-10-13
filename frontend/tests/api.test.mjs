// Execute the existing API wrapper with isolated transport doubles. No backend writes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function client(respond, platform = 'web') {
  const requests = [];
  const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  runInNewContext(compiled, {
    exports, require: (name) => { assert.equal(name, 'react-native'); return { Platform: { OS: platform } }; },
    process: { env: { EXPO_PUBLIC_API_URL: 'http://test-only' } },
    FormData: platform === 'web' ? FormData : class extends Map { append(key,value) { this.set(key,value); } },
    Blob, AbortController, setTimeout, clearTimeout, Error, TypeError,
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url === 'fixture-image') return { blob: async () => new Blob(['temporary test bytes'], { type: 'image/png' }) };
      if (respond) return respond(url, options);
      return { ok: true, json: async () => ({ id: 'saved-test-record', analysis_status: 'not_requested' }) };
    },
  });
  return { api: exports.api, requests };
}

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
  const {api,requests}=client(undefined,'android');
  const image={uri:'file:///cache/fresh-camera.jpg',fileName:'fresh-camera.jpg',mimeType:'image/jpeg'};
  await api.validateImage(image);await api.checkSuitability(image);
  await api.scan('plant-a',image,{}, {request_id:'camera-analysis-001'});
  assert.deepEqual(requests.map(r=>r.url),['http://test-only/validate-image','http://test-only/check-plant-suitability',
    'http://test-only/plants/plant-a/observations']);
  for(const {options} of requests) {
    assert.equal(options.body.get('image').uri,image.uri);
    assert.equal(options.body.get('image').name,image.fileName);
    assert.equal(options.body.get('image').type,'image/jpeg');
    assert.equal(options.headers,undefined); // The runtime supplies the multipart boundary.
  }
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
  } finally {URL.revokeObjectURL(uri);}
});
