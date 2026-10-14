// UI contract fixtures only; no real predictions, measurements or network calls.
import test from 'node:test';
import assert from 'node:assert/strict';
import { homeHealthSummary, recordLabels, progressionLabel, observationTime, retryId, scanBlockers, isTomato } from '../src/recordState.ts';

test('tomato analysis prerequisites require an explicitly tomato crop and every real check', () => {
  const ready = { busy:false,selected:{id:'p',crop_name:'tomato'},image:{uri:'photo'},validation:{is_valid:true},
    suitability:{status:'accepted'},health:{capabilities:{tomato_analysis:true,record_only:true}},pendingAnalysis:null,
    temperature:'',humidity:'',soilType:'',condition:'Normal' };
  assert.deepEqual(scanBlockers(ready,true),[]);
  for (const selected of [null,{id:'leaf',name:'Leaf',crop_name:'Leaf'},{id:'missing',name:'tomato',crop_name:null}]) {
    assert.ok(scanBlockers({...ready,selected},true).some(reason=>/crop set to tomato/.test(reason)));
  }
  assert.equal(isTomato({name:'tomato',crop_name:null}),false);
  for (const patch of [{image:null},{validation:null},{validation:{is_valid:false}},{suitability:{status:'unavailable'}},{health:{capabilities:{tomato_analysis:false,record_only:true}}}]) {
    assert.ok(scanBlockers({...ready,...patch},true).length>0);
  }
  assert.deepEqual(scanBlockers({...ready,selected:{id:'leaf',crop_name:'potato'}},false),[]);
});

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
  assert.doesNotMatch(labels.notice, /Experimental AI prediction/);
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

test('real predictions are marked experimental, unvalidated and uncalibrated with no fabricated severity', () => {
  const labels = recordLabels({ analysis_status: 'completed', disease: 'Early_blight', confidence: 72.5, severity: null, is_mock: false });
  assert.equal(labels.disease, 'Early_blight');
  assert.equal(labels.confidence, '72.5% prediction score (uncalibrated)');
  assert.equal(labels.severity, 'Severity not measured');
  assert.match(labels.notice, /Experimental AI prediction — not a validated diagnosis/);
  assert.match(labels.notice, /do not represent verified correctness/);
  assert.match(labels.notice, /may be wrong/);
  assert.match(labels.notice, /screening does not establish tomato identity/);
});

test('completed mock predictions never receive the real experimental AI label', () => {
  const labels = recordLabels({ analysis_status: 'completed', disease: 'Early_blight', confidence: 90, severity: null, is_mock: true });
  assert.match(labels.notice, /DEVELOPMENT MOCK/);
  assert.doesNotMatch(labels.notice, /Experimental AI prediction/);
  assert.equal(labels.severity, 'Severity not measured');
});

test('automatic observation timestamp captures local timezone and offset', async () => {
  const { captureObservation } = await import('../src/recordState.ts');
  const date = new Date('2025-01-01T06:30:00Z');
  date.getTimezoneOffset = () => -330;
  const captured = captureObservation(date);
  assert.equal(captured.observedAt, '2025-01-01T06:30:00.000Z');
  assert.match(captured.observedTimezone, /UTC\+05:30/);
});

test('button gates preserve crop, image, readiness, context and retry safety', async () => {
  const { scanBlockers, isTomato } = await import('../src/recordState.ts');
  const valid = { busy: false, selected: { crop_name: ' Tomato ' }, image: {}, validation: { is_valid: true }, suitability: { status: 'accepted' }, health: { capabilities: { tomato_analysis: true, record_only: true } }, pendingAnalysis: null, temperature: '25', humidity: '60', soilType: 'Loamy', condition: 'Wet' };
  assert.deepEqual(scanBlockers(valid, true), []);
  assert.equal(isTomato({ name: 'Tomato', crop_name: null }), false);
  for (const patch of [{ suitability: { status: 'not_checked' } }, { suitability: { status: 'rejected' } }, { suitability: { status: 'inconclusive' } }, { suitability: { status: 'unavailable' } }, { busy: true }, { selected: null }, { selected: { crop_name: 'potato' } }, { image: null }, { validation: null }, { validation: { is_valid: false } }, { health: null }, { health: { capabilities: { tomato_analysis: false, record_only: true } } }, { pendingAnalysis: false }, { temperature: 'invalid' }, { humidity: '101' }, { soilType: 'x'.repeat(101) }, { condition: 'unknown' }]) {
    assert.ok(scanBlockers({ ...valid, ...patch }, true).length, JSON.stringify(patch));
  }
  assert.deepEqual(scanBlockers({ ...valid, selected: { crop_name: 'potato' }, health: { capabilities: { tomato_analysis: false, record_only: true } } }, false), []);
  const recordOnly = { ...valid, temperature: '', humidity: '', soilType: '' };
  assert.deepEqual(scanBlockers(recordOnly, false), []);
  for (const patch of [{ temperature: '-50.1' }, { temperature: '70.1' }, { temperature: 'NaN' }, { humidity: '-0.1' }, { humidity: '100.1' }, { humidity: 'Infinity' }, { soilType: 'x'.repeat(101) }]) {
    assert.ok(scanBlockers({ ...recordOnly, ...patch }, false).length, JSON.stringify(patch));
  }
});

test('prediction display rounds long decimals without modifying the saved score', () => {
  const record={analysis_status:'completed',disease:'Bacterial_spot',severity:null,confidence:99.65035915374756,is_mock:false};
  assert.equal(recordLabels(record).confidence,'99.7% prediction score (uncalibrated)');
  assert.equal(record.confidence,99.65035915374756);
});
