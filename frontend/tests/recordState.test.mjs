// UI contract fixtures only; no real predictions, measurements or network calls.
import test from 'node:test';
import assert from 'node:assert/strict';
import { homeHealthSummary, recordLabels, progressionLabel, observationTime, retryId } from '../src/recordState.ts';

test('home requires multiple observations before discussing comparison', () => {
  for (const records of [undefined, [], [{ severity: null }], [{ severity: 0 }]]) {
    assert.equal(homeHealthSummary(records), 'Insufficient data');
  }
});
test('home reports unmeasured severity only when all observations lack severity', () => {
  assert.equal(homeHealthSummary([{ severity: null }, { severity: null }]),
    'Progression unavailable because severity was not measured.');
});
test('home acknowledges zero, mixed and synthetic stored severity without inferring progression', () => {
  for (const records of [
    [{ severity: null }, { severity: 0 }],
    [{ severity: 0 }, { severity: 25 }],
    [{ severity: 20, is_mock: true }, { severity: 30, is_mock: true }],
  ]) {
    assert.equal(homeHealthSummary(records),
      'Stored severity values are available. Open the health dashboard for comparison availability.');
  }
});

test('record-only labels never invent diagnosis, confidence or severity', () => {
  const labels = recordLabels({ analysis_status: 'not_requested', disease: null, severity: null, confidence: null, is_mock: false });
  assert.equal(labels.disease, 'Disease not assessed');
  assert.equal(labels.severity, 'Severity not measured');
  assert.equal(labels.confidence, 'Confidence unavailable');
  assert.match(labels.notice, /without analysis/);
});
test('unknown severity stays missing; an explicitly stored zero stays zero', () => {
  const base = { analysis_status: 'completed', disease: 'test-only', confidence: null, is_mock: false };
  assert.equal(recordLabels({ ...base, severity: null }).severity, 'Severity not measured');
  assert.equal(recordLabels({ ...base, severity: 0 }).severity, '0% recorded severity');
});
test('legacy mock values remain labelled synthetic', () => {
  const labels = recordLabels({ analysis_status: 'legacy_unknown', disease: 'test-only', severity: 20, confidence: 30, is_mock: true });
  assert.match(labels.severity, /synthetic demo/);
  assert.match(labels.confidence, /synthetic/);
  assert.match(labels.notice, /not a diagnosis/);
});
test('unavailable or incomplete comparison never displays a positive health label', () => {
  assert.equal(progressionLabel({ status: 'insufficient_data' }), 'Insufficient data');
  assert.equal(progressionLabel({ status: 'unavailable', delta: -5 }), 'Progression unavailable');
  assert.equal(progressionLabel({ status: 'stable', delta: null }), 'Progression unavailable');
  assert.equal(progressionLabel({ status: 'improving', delta: -5, policy_version: null }), 'Progression unavailable');
});
test('retry reuses pending identity and creates no new submission ID', () => {
  let calls = 0;
  const create = () => { calls++; return 'new-request'; };
  assert.equal(retryId(null, create), 'new-request');
  assert.equal(retryId('pending-request', create), 'pending-request');
  assert.equal(retryId('pending-request', create), 'pending-request');
  assert.equal(calls, 1);
});
test('observation time remains unknown or explicitly timezone-qualified', () => {
  assert.equal(observationTime(''), null);
  assert.equal(observationTime('2025-01-01T12:00:00+05:30'), '2025-01-01T06:30:00.000Z');
  assert.throws(() => observationTime('2025-01-01T12:00:00'));
  assert.throws(() => observationTime('2999-01-01T00:00:00Z'));
  assert.throws(() => observationTime('invalid'));
  assert.throws(() => observationTime('2025-02-30T00:00:00Z'));
});
