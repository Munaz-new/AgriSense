// Storage contract tests use an IndexedDB double, not a real browser persistence claim.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import ts from 'typescript';

function storage(available=true) {
  const data=new Map();
  const exports={};
  const db={close(){},transaction(){
    let aborted=false;
    const tx={abort(){aborted=true;queueMicrotask(()=>tx.onabort?.());},objectStore(){return store;}};
    function request(action){const r={};queueMicrotask(()=>{if(aborted)return;try{r.result=action();r.onsuccess?.();}catch{tx.abort();}});return r;}
    const store={transaction:tx,get:key=>request(()=>structuredClone(data.get(key))),put:(value,key)=>request(()=>{data.set(key,structuredClone(value));return key;}),delete:key=>request(()=>data.delete(key))};
    setTimeout(()=>{if(!aborted)tx.oncomplete?.();},0);
    return tx;
  }};
  const indexedDB={open(){const r={result:db};queueMicrotask(()=>r.onsuccess?.());return r;}};
  const source=readFileSync(new URL('../src/draftStore.ts',import.meta.url),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  runInNewContext(code,{exports,Blob,Error,setTimeout,clearTimeout,...(available?{indexedDB}:{}),require:()=>({API_URL:'http://fixture',imageBlob:async()=>new Blob(['exact test photo bytes'],{type:'image/png'})})});
  return {api:exports,data};
}
const fields={plantId:'plant-1',temperature:'21.5',humidity:'0',soilType:'Sandy loam',condition:'Normal',observedAt:'',observedTimezone:'',trackingRef:'leaf-a',notes:'private test note',pendingId:'request-0001',pendingAnalysis:false};

test('draft photo, optional strings and retry identity survive store/reload and explicit removal',async()=>{
  const {api}=storage();
  assert.equal(await api.writeDraft(fields,{uri:'fixture',fileName:'leaf.png'}),true);
  const recovered=await api.readDraft();
  assert.equal(recovered.pendingId,fields.pendingId);
  assert.equal(recovered.pendingAnalysis,false);
  assert.equal(recovered.temperature,'21.5');assert.equal(recovered.humidity,'0');
  assert.equal(await recovered.photo.text(),'exact test photo bytes');
  await api.removeDraft();assert.equal(await api.readDraft(),null);
});
test('a different uncertain submission cannot overwrite a pending recovery copy',async()=>{
  const {api}=storage();
  await api.writeDraft(fields,{uri:'fixture'});
  await assert.rejects(api.writeDraft({...fields,pendingId:'request-0002'},{uri:'fixture'}),/Recovery storage/);
  assert.equal((await api.readDraft()).pendingId,fields.pendingId);
  await api.writeDraft(fields,{uri:'fixture'}); // identical retry allowed
});
test('unavailable native storage remains explicit and damaged drafts fail closed',async()=>{
  const native=storage(false).api;
  assert.equal(native.draftStorageAvailable(),false);
  assert.equal(await native.writeDraft(fields,{uri:'fixture'}),false);
  assert.equal(await native.readDraft(),null);
  const {api,data}=storage();data.set('http://fixture',{version:2});
  await assert.rejects(api.readDraft(),/incompatible or damaged/);
  assert.equal(api.validStoredDraft({...fields,version:1,photo:new Blob([]),fileName:'leaf.png',mimeType:'image/png'}),false);
  await assert.rejects(api.writeDraft({...fields,soilType:'x'.repeat(101)},{uri:'fixture'}),/field lengths/);
});
