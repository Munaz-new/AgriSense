// Exercise the real hook with a minimal state harness and isolated API doubles.
// No React renderer, browser, network, or project database is needed.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';
import * as recordState from '../src/recordState.ts';

class PlantSuitabilityError extends Error {
  constructor(code, message) { super(message); this.code = code; }
}
function journalHarness(api, picker = {}, drafts = {}, camera = {}) {
  api = { checkSuitability: async () => ({ outcome: 'plant', message: 'Leaf content supported' }), ...api };
  const state = [];
  let cursor = 0;
  const react = {
    useRef(initial) {
      const index = cursor++;
      if (index === state.length) state.push({ current: initial });
      return state[index];
    },
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
  const imagePicker = { launchImageLibraryAsync: async () => ({ canceled: false, assets: [{ uri: 'test-image' }] }),
    CameraType: { back: 'back' }, ...picker };
  const captureExports = {};
  runInNewContext(ts.transpileModule(readFileSync(new URL('../src/photoCapture.ts', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports: captureExports, Error, require: () => imagePicker });
  runInNewContext(compiled, {
    exports, Error, URL, AbortController,
    require(name) {
      if (name === 'react') return react;
      if (name === '../api') return { api, PlantSuitabilityError, ImageValidationError: class extends Error {} };
      if (name === '../recordState') return recordState;
      if (name === '../draftStore') return { draftStorageAvailable: () => false, writeDraft: async () => false, readDraft: async () => null, removeDraft: async () => {}, ...drafts };
      if (name === 'expo-image-picker') return imagePicker;
      if (name === 'react-native') return { Platform: { OS: camera.platform || 'android' } };
      if (name === '../photoCapture') return captureExports;
      if (name === '../browserCamera') return { captureBrowserPhoto: camera.capture };
      throw new Error(`Unexpected import: ${name}`);
    },
  });
  return () => { cursor = 0; return exports.useJournal(); };
}

test('two save taps before a render submit one request and persist its identity before sending', async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const events = [];
  const render = journalHarness({
    health: async () => ({ capabilities: { record_only: true } }), plants: async () => [{ id:'p' }], observations: async () => [],
    validateImage: async () => ({ is_valid:true }),
    record: async (...args) => { events.push(['submit',args[3].request_id]); await pending; return { id:'r',created_at:'2025-01-01' }; },
  }, {}, { writeDraft: async draft => { events.push(['persist',draft.pendingId]); return true; } });
  await render().refresh(); await render().pick(false); await render().validateImage(); render().setCondition('Normal');
  const staleRender = render();
  const first = staleRender.saveRecord(); const second = staleRender.saveRecord();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(events.length,2);
  assert.deepEqual(events.map(e => e[0]),['persist','submit']);
  assert.equal(events[0][1],events[1][1]);
  finish(); await Promise.all([first,second]);
});

test('storage failure prevents transmission and allows a later save', async () => {
  let fail=true, calls=0;
  const render=journalHarness({ health: async () => ({ capabilities:{record_only:true} }),
    plants:async()=>[{id:'p'}],observations:async()=>[],validateImage:async()=>({is_valid:true}),
    record:async()=>{calls++;return {id:'r',created_at:'2025-01-01'};},
  },{}, {writeDraft:async()=>{if(fail)throw new Error('storage full');return true;}});
  await render().refresh();await render().pick(false);await render().validateImage();render().setCondition('Normal');
  await render().saveRecord();assert.equal(calls,0);assert.equal(render().pendingId,null);assert.match(render().error,/storage full/);
  fail=false;await render().saveRecord();assert.equal(calls,1);
});

test('recovering an already saved request opens its record without resubmitting', async () => {
  let deleted=0;
  const row={id:'saved',request_id:'pending-001',created_at:'2025-01-01'};
  const render=journalHarness({plants:async()=>[{id:'p'}],observations:async()=>[row]}, {}, {
    readDraft:async()=>({plantId:'p',pendingId:'pending-001'}),removeDraft:async()=>{deleted++;},
  });
  await render().restoreDraft();assert.equal(render().screen,'result');assert.equal(render().result,row);assert.equal(deleted,1);
});

test('recovering an uncertain save retains identity and requires new photo checks', async () => {
  const draft={plantId:'p',pendingId:'pending-001',pendingAnalysis:false,photo:new Blob(['photo']),
    fileName:'leaf.jpg',mimeType:'image/jpeg',temperature:'',humidity:'0',soilType:'',condition:'Normal',
    observedAt:'2025-01-01T00:00:00Z',observedTimezone:'UTC',trackingRef:'',notes:'draft notes'};
  const render=journalHarness({plants:async()=>[{id:'p'}],observations:async()=>[]},{},{readDraft:async()=>draft});
  await render().restoreDraft();assert.equal(render().pendingId,draft.pendingId);assert.equal(render().locked,true);
  assert.equal(render().humidity,'0');assert.equal(render().temperature,'');assert.equal(render().validation,null);
  assert.equal(render().suitability.status,'not_checked');assert.ok(render().image.uri.startsWith('blob:'));
  render().clearDraft();
});

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


test('analysis retries preserve request ID and mode; record-only remains separate', async () => {
  const calls = [];
  let fail = true;
  const plant = { id: 'tomato-a', crop_name: 'tomato' };
  const render = journalHarness({
    health: async () => ({ capabilities: { record_only: true, tomato_analysis: true } }),
    plants: async () => [plant], observations: async () => [],
    validateImage: async () => ({ is_valid: true }),
    scan: async (...args) => {
      calls.push(args);
      if (fail) throw new Error('timeout');
      return { id: 'saved', plant_id: plant.id, created_at: '2025-01-01', severity: null };
    },
    record: async () => { throw new Error('wrong save path'); },
  });
  await render().refresh();
  await render().pick(false);
  await render().validateImage();
  render().setTemperature('25'); render().setHumidity('60'); render().setSoilType('Loamy'); render().setCondition('Normal');
  await render().saveRecord(true);
  const pending = render().pendingId;
  assert.ok(pending);
  assert.equal(render().pendingAnalysis, true);
  await render().saveRecord(false);
  assert.match(render().error, /Retry the same action/);
  assert.equal(calls.length, 1);
  fail = false;
  await render().saveRecord(true);
  assert.equal(calls.length, 2);
  assert.equal(calls[0][3].request_id, pending);
  assert.equal(calls[1][3].request_id, pending);
  assert.equal(render().pendingId, null);
  assert.equal(render().pendingAnalysis, null);
  assert.equal(render().screen, 'result');
});

test('photo capture, crop selection, validation, automatic details and saved history', async () => {
  const tomato = { id: 'tomato', crop_name: ' Tomato ' };
  const other = { id: 'other', name: 'Tomato', crop_name: null };
  let valid = false;
  let saved;
  const render = journalHarness({
    health: async () => ({ capabilities: { tomato_analysis: true, record_only: true } }),
    plants: async () => [other, tomato], observations: async () => saved ? [saved] : [],
    progression: async () => ({ status: 'unavailable' }),
    validateImage: async () => ({ is_valid: valid, message: 'test validation' }),
    scan: async (id, image, env, details) => {
      assert.equal(id, tomato.id);
      assert.equal(details.tracking_ref, null);
      assert.equal(details.notes, 'User note');
      assert.ok(details.observed_at && details.observed_timezone);
      saved = { ...details, id: 'saved', plant_id: id, created_at: new Date().toISOString() };
      return saved;
    },
  });
  await render().refresh();
  assert.ok(render().analysisBlockers.some(r => /crop set to tomato/.test(r)));
  await render().pick(false);
  assert.ok(render().observedAt && render().observedTimezone);
  assert.equal(render().condition, '');
  await render().validateImage();
  assert.equal(render().validation.is_valid, false);
  render().selectPlant(tomato);
  assert.equal(render().image, null);
  assert.equal(render().validation, null);
  await render().pick(false);
  const timestamp = render().observedAt;
  valid = true;
  await render().validateImage();
  render().setTemperature('25'); render().setHumidity('60'); render().setSoilType('Loam'); render().setCondition('Dry'); render().setNotes('User note');
  assert.equal(render().analysisBlockers.length, 0);
  await render().saveRecord(true);
  assert.equal(saved.observed_at, timestamp);
  assert.equal(render().records.tomato[0].id, 'saved');
  await render().openHistory('history');
  assert.equal(render().observations[0].id, 'saved');
  await render().pick(false);
  assert.equal(render().validation, null);
});

test('explicit tomato creation selects persisted crop and image analysis needs no environment', async () => {
  let fields;
  const render = journalHarness({
    health: async () => ({ capabilities: { tomato_analysis: true, record_only: true } }),
    plants: async () => [], observations: async () => [],
    addPlant: async (name, crop) => {
      assert.equal(crop, 'tomato');
      return { id: 'new', name, crop_name: crop };
    },
    validateImage: async () => ({ is_valid: true, reason: 'technical_checks_passed' }),
    scan: async (id, image, env, details) => {
      fields = env;
      return { id: 'saved', plant_id: id, ...details, created_at: new Date().toISOString() };
    },
  });
  await render().refresh();
  render().setName('Tomato'); render().setCropName('tomato');
  await render().addPlant();
  assert.equal(render().selected.crop_name, 'tomato');
  await render().pick(false); await render().validateImage();
  assert.equal(render().result, null); // Validation never diagnoses healthy or diseased.
  assert.equal(render().analysisBlockers.length, 0);
  assert.ok(render().recordBlockers.length);
  await render().saveRecord(true);
  assert.deepEqual({ ...fields }, { temperature: null, humidity: null, soil_type: null, soil_condition: null });
});

function scanApi(extra = {}) {
  return { health: async () => ({ capabilities: { tomato_analysis: true, record_only: true, plant_content_screening: true } }),
    plants: async () => [{ id: 'p', crop_name: 'tomato' }], observations: async () => [],
    validateImage: async () => ({ is_valid: true, message: 'Technical checks passed' }),
    scan: async () => ({ id: 'saved', created_at: '2026-01-01', analysis_status: 'completed' }), ...extra };
}
test('new photo replaces preview asset and clears previous result, file validation and suitability', async () => {
  let asset = { uri: 'leaf-uri', fileName: 'leaf.jpg' };
  const render = journalHarness(scanApi(), { launchImageLibraryAsync: async () => ({ canceled: false, assets: [asset] }) });
  await render().refresh(); await render().pick(false); await render().validateImage();
  assert.equal(render().suitability.status, 'accepted');
  await render().saveRecord(true);
  assert.equal(render().result.id, 'saved');
  asset = { uri: 'logo-uri', fileName: 'logo.png' };
  await render().pick(false);
  assert.equal(render().image, asset);
  assert.equal(render().imageRevision, 2);
  assert.equal(render().result, null);
  assert.equal(render().validation, null);
  assert.equal(render().suitability.status, 'not_checked');
  assert.equal(render().records.p.length, 1);
});
for (const code of ['non_plant_image', 'plant_content_uncertain']) {
  test(`${code} at analysis clears retry lock and allows a replacement photo without saving`, async () => {
    const render = journalHarness(scanApi({ scan: async () => { throw new PlantSuitabilityError(code, 'Use another leaf photo'); } }));
    await render().refresh(); await render().pick(false); await render().validateImage();
    await render().saveRecord(true);
    assert.equal(render().pendingId, null);
    assert.equal(render().locked, false);
    assert.equal(render().suitability.status, code === 'non_plant_image' ? 'rejected' : 'inconclusive');
    assert.equal(render().error, 'Use another leaf photo');
    assert.equal(render().records.p.length, 0);
    assert.equal(render().result, null);
    await render().pick(false);
    assert.equal(render().error, '');
    assert.equal(render().suitability.status, 'not_checked');
  });
}
test('logo passes file validation but fails suitability and cannot start disease analysis', async () => {
  let scans = 0;
  const render = journalHarness(scanApi({ checkSuitability: async () => { throw new PlantSuitabilityError('non_plant_image', 'Logo rejected'); }, scan: async () => { scans++; } }));
  await render().refresh(); await render().pick(false); await render().validateImage();
  assert.equal(render().validation.is_valid, true);
  assert.equal(render().suitability.status, 'rejected');
  await render().saveRecord(true);
  assert.equal(scans, 0);
  assert.equal(render().pendingId, null);
});
test('screening service failure keeps file validation but never marks plant suitability accepted', async () => {
  const render = journalHarness(scanApi({ checkSuitability: async () => { throw new PlantSuitabilityError('plant_screening_unavailable', 'Screening unavailable'); } }));
  await render().refresh(); await render().pick(false); await render().validateImage();
  assert.equal(render().validation.is_valid, true);
  assert.equal(render().suitability.status, 'unavailable');
  assert.ok(render().analysisBlockers.length);
  assert.equal(render().result, null);
});
test('late suitability response cannot approve a discarded draft', async () => {
  let finish, entered;
  const started = new Promise(resolve => { entered = resolve; });
  const render = journalHarness(scanApi({ checkSuitability: () => new Promise(resolve => { finish = resolve; entered(); }) }));
  await render().refresh(); await render().pick(false);
  const pending = render().validateImage();
  await started;
  assert.equal(render().suitability.status, 'checking');
  render().clearDraft();
  finish({ outcome: 'plant', message: 'Leaf' }); await pending;
  assert.equal(render().image, null);
  assert.equal(render().validation, null);
  assert.equal(render().suitability.status, 'not_checked');
});
test('canceling picker retains the current image and its checks', async () => {
  let canceled = false;
  const render = journalHarness(scanApi(), { launchImageLibraryAsync: async () => ({ canceled, assets: [{ uri: 'leaf' }] }) });
  await render().refresh(); await render().pick(false); await render().validateImage();
  const asset = render().image;
  canceled = true; await render().pick(false);
  assert.equal(render().image, asset);
  assert.equal(render().suitability.status, 'accepted');
});

test('plant creation timeout retries the same identity and does not duplicate a refreshed plant', async () => {
  const calls=[]; let saved=null;
  const render=journalHarness({health:async()=>({capabilities:{record_only:true}}),
    plants:async()=>saved?[saved]:[],observations:async()=>[],
    addPlant:async(name,crop,id)=>{calls.push({name,crop,id});
      if(!saved){saved={id:'plant-saved',name,crop_name:crop};throw new Error('timeout');}
      return saved;
    }});
  await render().refresh();render().setName('Plant A');render().setCropName('tomato');
  await render().addPlant();assert.equal(render().locked,true);assert.ok(render().pendingPlant);
  await render().refresh();assert.equal(render().plants.length,1);
  await render().addPlant();assert.deepEqual(calls[0],calls[1]);
  assert.equal(render().plants.length,1);assert.equal(render().pendingPlant,null);
});

test('blocked selection cannot display another plant history under the selected name', async () => {
  const a={id:'a'},b={id:'b'};let histories=0;
  const render=journalHarness({health:async()=>({capabilities:{record_only:true}}),plants:async()=>[a,b],
    observations:async()=>{histories++;return [];},progression:async()=>({status:'unavailable'})}, {},
    {removeDraft:async()=>{throw new Error('storage unavailable');}});
  await render().refresh();render().clearDraft();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(render().draftAvailable,true);
  const before=histories;await render().openHistory('history',b);
  assert.equal(histories,before);assert.equal(render().selected.id,'a');
  assert.notEqual(render().screen,'history');assert.match(render().error,/restore or discard/);
});

test('definitive analysis rejection clears recovery identity before a new save', async () => {
  let stored=null, reject=true;
  const render=journalHarness(scanApi({scan:async()=>{
    if(reject)throw new PlantSuitabilityError('plant_content_uncertain','Try another photo');
    return {id:'saved',created_at:'2026-01-01'};
  }}),{}, {writeDraft:async fields=>{
    if(stored?.pendingId&&stored.pendingId!==fields.pendingId)throw new Error('conflicting draft');
    stored=fields;return true;
  },removeDraft:async()=>{stored=null;}});
  await render().refresh();await render().pick(false);await render().validateImage();
  await render().saveRecord(true);assert.equal(stored,null);assert.equal(render().pendingId,null);
  reject=false;await render().validateImage();await render().saveRecord(true);
  assert.equal(render().result.id,'saved');
});

test('preview rejection cannot unlock an earlier uncertain save or erase its recovery identity', async () => {
  let reject=false,stored=null;
  const render=journalHarness(scanApi({scan:async()=>{throw new Error('timeout');},
    checkSuitability:async()=>{if(reject)throw new PlantSuitabilityError('plant_content_uncertain','Try again');
      return {outcome:'plant',message:'Accepted'};}}),{},
    {writeDraft:async fields=>{stored=fields;return true;},removeDraft:async()=>{stored=null;}});
  await render().refresh();await render().pick(false);await render().validateImage();await render().saveRecord(true);
  const identity=render().pendingId;assert.ok(identity);
  reject=true;await render().validateImage();
  assert.equal(render().pendingId,identity);assert.equal(stored.pendingId,identity);assert.equal(render().locked,true);
});

test('rapid history taps cannot relabel an in-flight history request', async () => {
  const a={id:'a'},b={id:'b'},c={id:'c'};let finish;
  const pending=new Promise(resolve=>{finish=resolve;});let loading=false;
  const render=journalHarness({health:async()=>({capabilities:{record_only:true}}),plants:async()=>[a,b,c],
    observations:async id=>{if(loading)await pending;return [{id,plant_id:id}];},progression:async()=>({status:'unavailable'})});
  await render().refresh();loading=true;
  const stale=render();const first=stale.openHistory('history',b);await stale.openHistory('history',c);
  finish();await first;
  assert.equal(render().selected.id,'b');assert.equal(render().observations[0].plant_id,'b');
});

test('native camera requests permission, previews fresh capture, retakes and cancels without uploading', async () => {
  let requests=0, launches=0, validations=0;
  const render=journalHarness(scanApi({validateImage:async()=>{validations++;return {is_valid:true};}}), {
    getCameraPermissionsAsync:async()=>({granted:false,canAskAgain:true}),
    requestCameraPermissionsAsync:async()=>{requests++;return {granted:true};},
    launchCameraAsync:async options=>{
      assert.equal(options.mediaTypes[0],'images');assert.equal(options.allowsEditing,false);
      assert.equal(options.cameraType,'back');launches++;
      return {canceled:false,assets:[{uri:`file:///camera-${launches}.jpg`,width:1200,height:1600}]};
    },
  });
  await render().refresh();await render().pick(true);
  assert.equal(requests,1);assert.equal(render().image.uri,'file:///camera-1.jpg');
  assert.equal(validations,0);assert.match(render().photoMessage,/Nothing has been uploaded/);
  await render().validateImage();assert.equal(render().suitability.status,'accepted');
  await render().pick(true);assert.equal(render().image.uri,'file:///camera-2.jpg');
  assert.equal(render().imageRevision,2);assert.equal(render().validation,null);
  assert.equal(render().suitability.status,'not_checked');assert.equal(render().result,null);
  render().cancelPhoto();assert.equal(render().image,null);assert.equal(render().pendingId,null);
  assert.match(render().photoMessage,/Photo canceled/);
});

for(const canAskAgain of [true,false]) test(`native permission denial is actionable (canAskAgain=${canAskAgain}) and gallery still works`,async()=>{
  let requests=0,launches=0;
  const render=journalHarness(scanApi(),{
    getCameraPermissionsAsync:async()=>({granted:false,canAskAgain}),
    requestCameraPermissionsAsync:async()=>{requests++;return {granted:false,canAskAgain};},
    launchCameraAsync:async()=>{launches++;},
  });
  await render().refresh();await render().pick(true);
  assert.equal(requests,canAskAgain?1:0);assert.equal(launches,0);assert.equal(render().busy,false);
  assert.match(render().error,canAskAgain?/permission was denied/:/phone settings/);
  await render().pick(false);assert.equal(render().image.uri,'test-image');assert.equal(render().error,'');
});

test('granted camera permission is not requested again; native cancellation retains prior image and validation',async()=>{
  const render=journalHarness(scanApi(),{
    getCameraPermissionsAsync:async()=>({granted:true}),
    requestCameraPermissionsAsync:async()=>assert.fail('must not request granted permission'),
    launchCameraAsync:async()=>({canceled:true,assets:null}),
  });
  await render().refresh();await render().pick(false);await render().validateImage();
  const previous=render().image;
  await render().pick(true);
  assert.equal(render().image,previous);assert.equal(render().validation.is_valid,true);
  assert.match(render().photoMessage,/Camera capture canceled/);assert.equal(render().busy,false);
});

for(const returned of [null,{canceled:false,assets:[]},{canceled:false,assets:[{uri:''}]},
  {canceled:false,assets:[{uri:'file:///empty.jpg',fileSize:0}]},
  {canceled:false,assets:[{uri:'file:///bad.jpg',width:0,height:1000}]}]) {
  test(`unavailable or empty camera result preserves a usable gallery photo: ${JSON.stringify(returned)}`,async()=>{
    const render=journalHarness(scanApi(),{
      getCameraPermissionsAsync:async()=>({granted:true}),
      launchCameraAsync:async()=>{if(returned===null)throw new Error('No camera');return returned;},
    });
    await render().refresh();await render().pick(false);const previous=render().image;
    await render().pick(true);assert.equal(render().image,previous);assert.equal(render().locked,false);
    assert.match(render().error,returned===null?/camera could not open/:/No usable photo/);
  });
}

test('camera analysis keeps one capture and save operation, preserves retry identity and blocks retake while uncertain',async()=>{
  let release,launches=0,scans=0;const identities=[];
  const render=journalHarness(scanApi({scan:async(id,image,env,details)=>{
    assert.equal(image.uri,'file:///fresh.jpg');identities.push(details.request_id);
    if(++scans===1)throw new Error('Cannot reach backend');
    return {id:'saved',created_at:'2026-01-01'};
  }}),{
    getCameraPermissionsAsync:async()=>({granted:true}),
    launchCameraAsync:async()=>{launches++;return await new Promise(resolve=>{release=resolve;});},
  });
  await render().refresh();const stale=render();const capture=stale.pick(true);await stale.pick(true);
  await new Promise(resolve=>setImmediate(resolve));assert.equal(launches,1);
  release({canceled:false,assets:[{uri:'file:///fresh.jpg',width:1200,height:1600}]});await capture;
  await render().validateImage();const saveView=render();await Promise.all([saveView.saveRecord(true),saveView.saveRecord(true)]);
  assert.equal(scans,1);assert.match(render().error,/Cannot reach backend/);assert.equal(render().result,null);
  const pending=render().pendingId;render().cancelPhoto();await render().pick(true);
  assert.equal(render().pendingId,pending);assert.equal(launches,1);
  await render().saveRecord(true);assert.deepEqual(identities,[pending,pending]);assert.equal(render().result.id,'saved');
});

test('web capture uses the browser adapter, aborts on navigation and leaves gallery independently usable',async()=>{
  let signal;
  const render=journalHarness(scanApi(),{
    getCameraPermissionsAsync:async()=>assert.fail('web must not use native permissions'),
    launchCameraAsync:async()=>assert.fail('web must not use file-picker camera fallback'),
  },{}, {platform:'web',capture:async input=>{
    signal=input;
    return new Promise(resolve=>input.addEventListener('abort',()=>resolve({canceled:true,assets:null})));
  }});
  await render().refresh();const capture=render().pick(true);assert.ok(signal);
  render().navigate('home');await capture;assert.equal(signal.aborted,true);
  assert.equal(render().image,null);assert.equal(render().busy,false);
  await render().pick(false);assert.equal(render().image.uri,'test-image');
});

test('web capture object URL is released when its preview is canceled',async()=>{
  const uri=URL.createObjectURL(new Blob(['fixture-photo']));
  const render=journalHarness(scanApi(),{},{},{platform:'web',capture:async()=>({canceled:false,assets:[{uri,width:640,height:480}]})});
  await render().refresh();await render().pick(true);
  assert.equal(await (await fetch(render().image.uri)).text(),'fixture-photo');
  render().cancelPhoto();await assert.rejects(fetch(uri));
});

test('native successful analysis shows the server result and retains it in refreshed history', async () => {
  const saved = { id:'native-saved', plant_id:'p', disease:'Early_blight', confidence:72.5,
    prediction_score:72.5, severity:null, is_mock:false, analysis_status:'completed', created_at:'2026-01-01' };
  let history = [];
  const render = journalHarness(scanApi({ observations:async()=>history, progression:async()=>({status:'unavailable'}),
    scan:async(id, image)=>{ assert.equal(image.uri,'file:///native.jpg'); history=[saved]; return saved; } }), {
    getCameraPermissionsAsync:async()=>({granted:true}),
    launchCameraAsync:async()=>({canceled:false,assets:[{uri:'file:///native.jpg',width:1200,height:1600}]}),
  });
  await render().refresh(); await render().pick(true); await render().validateImage(); await render().saveRecord(true);
  assert.equal(render().screen,'result'); assert.equal(render().result,saved);
  assert.equal(render().pendingId,null); assert.equal(render().image,null);
  await render().openHistory('history'); assert.deepEqual(render().observations,[saved]);
  assert.equal(render().result.severity,null); assert.equal(render().result.confidence,72.5);
});

test('upload serialization error stays a photo-check error; retry can then pass screening', async () => {
  let failing=true;
  const render=journalHarness(scanApi({checkSuitability:async()=>{
    if(failing) throw new Error('Unsupported FormDataPart implementation');
    return {outcome:'plant',message:'Plant content supported'};
  }}));
  await render().refresh(); await render().pick(false); await render().validateImage();
  assert.equal(render().suitability.status,'not_checked');
  assert.match(render().error,/Unsupported FormDataPart implementation/);
  assert.match(render().suitability.message,/not been determined/);
  failing=false; await render().validateImage();
  assert.equal(render().suitability.status,'accepted');
  assert.equal(render().error,'');
});
