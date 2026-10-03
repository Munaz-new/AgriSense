// Exercise the real hook with a minimal state harness and isolated API doubles.
// No React renderer, browser, network, or project database is needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function journalHarness(api) {
  const state = [];
  let cursor = 0;
  const react = {
    useEffect() {}, // Explicitly refresh below instead of scheduling mount effects.
    useState(initial) {
      const index = cursor++;
      if (index === state.length) state.push(initial);
      return [state[index], value => {
        state[index] = typeof value === 'function' ? value(state[index]) : value;
      }];
    },
  };
  const source = readFileSync(new URL('../src/hooks/useJournal.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  runInNewContext(compiled, {
    exports, Error,
    require(name) {
      if (name === 'react') return react;
      if (name === '../api') return { api, ImageValidationError: class extends Error {} };
      if (name === 'expo-image-picker' || name === '../recordState') return {};
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  return () => { cursor = 0; return exports.useJournal(); };
}

for (const failurePoint of ['health', 'plants', 'observations']) {
  test(`failed ${failurePoint} refresh clears connected state and a later success reconnects`, async () => {
    const status = { capabilities: { record_only: true } };
    const plant = { id: 'plant-a', name: 'Test plant' };
    const records = [{ id: 'record-a', severity: null }];
    let failing = false;
    const response = (name, value) => async () => {
      if (failing && failurePoint === name) throw new Error('Service unavailable');
      return value;
    };
    const render = journalHarness({
      health: response('health', status),
      plants: response('plants', [plant]),
      observations: response('observations', records),
    });

    await render().refresh();
    assert.equal(render().health, status);
    assert.equal(render().selected, plant);
    assert.equal(render().records[plant.id], records);

    failing = true;
    await render().refresh();
    const failed = render();
    assert.equal(failed.health, null);
    assert.equal(failed.error, 'Service unavailable');
    assert.equal(failed.busy, false);
    assert.equal(failed.selected, plant);
    assert.equal(failed.records[plant.id], records);

    failing = false;
    await render().refresh();
    assert.equal(render().health, status);
    assert.equal(render().error, '');
    assert.equal(render().busy, false);
  });
}
