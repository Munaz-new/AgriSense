// Execute the existing API wrapper with isolated transport doubles. No backend writes.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function client() {
  const requests = [];
  const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  runInNewContext(compiled, {
    exports, require: (name) => { assert.equal(name, 'react-native'); return { Platform: { OS: 'web' } }; },
    process: { env: { EXPO_PUBLIC_API_URL: 'http://test-only' } },
    FormData, Blob, AbortController, setTimeout, clearTimeout,
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (url === 'fixture-image') return { blob: async () => new Blob(['temporary test bytes'], { type: 'image/png' }) };
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
  const saves = requests.filter(item => item.options);
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
