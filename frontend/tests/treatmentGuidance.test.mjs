import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { TOMATO_GUIDANCE, treatmentGuidance, GUIDANCE_LIMITATIONS } from '../src/treatmentGuidance.ts';

const modelClasses = JSON.parse(readFileSync(new URL('../../model/configs/tomato.json', import.meta.url))).class_names;
const real = disease => ({ disease, is_mock: false, analysis_status: 'completed' });

test('guidance covers exactly the trained class mapping with explicit unsupported guidance', () => {
  assert.deepEqual(Object.keys(TOMATO_GUIDANCE).sort(), [...modelClasses].sort());
  for (const name of modelClasses) {
    const guidance = treatmentGuidance(real(name));
    assert.ok(guidance.steps.length);
    if (name !== 'healthy' && !guidance.unavailable) {
      assert.ok(guidance.sources.length);
      for (const source of guidance.sources) {
        const url = new URL(source.url);
        assert.equal(url.protocol, 'https:');
        assert.ok(['extension.umn.edu', 'ipm.ucanr.edu'].includes(url.hostname));
      }
    }
  }
  assert.equal(treatmentGuidance(real('Target_Spot')).unavailable, true);
  for (const unknown of [null, 'unknown', 'Early Blight', 'toString', '__proto__']) {
    assert.equal(treatmentGuidance(real(unknown)).unavailable, true);
  }
});

test('mock, record-only, and legacy observations never receive model-derived treatment advice', () => {
  for (const patch of [{ is_mock: true }, { analysis_status: 'not_requested' }, { analysis_status: 'legacy_unknown' }]) {
    assert.equal(treatmentGuidance({ ...real('Early_blight'), ...patch }), null);
  }
});

test('healthy is not a guarantee and guidance does not mutate the prediction', () => {
  const input = Object.freeze(real('healthy'));
  assert.match(treatmentGuidance(input).steps.join(' '), /does not rule out disease/);
  assert.match(GUIDANCE_LIMITATIONS, /not a diagnosis/);
  assert.match(GUIDANCE_LIMITATIONS, /locally approved labels/);
  assert.equal(input.disease, 'healthy');
});
