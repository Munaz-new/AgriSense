import test from 'node:test';
import assert from 'node:assert/strict';
import { loadTs } from './nativeRuntime.mjs';

const sent = [];
class XHR {
  constructor() { sent.push(this); }
  open(method, url) { this.method=method; this.url=url; }
  send(body) { this.body=body; }
  abort() { this.didAbort=true; this.onabort?.(); }
  getResponseHeader(name) { return name.toLowerCase()==='x-test'?'value':null; }
  setRequestHeader() { assert.fail('XHR supplies the multipart boundary'); }
}
const { nativeMultipartUpload } = loadTs('../src/nativeMultipartUpload.ts', { XMLHttpRequest: XHR });

function form(uri='file:///camera.jpg') {
  const value = new globalThis.FormData();
  value.append('image', { uri, name:'leaf.jpg', type:'image/jpeg' });
  return value;
}

test('native XHR sends the original React Native FormData without rewriting parts', async () => {
  const controller=new AbortController(), body=form();
  const pending=nativeMultipartUpload('http://192.168.1.5:8000/validate-image',body,controller.signal);
  const xhr=sent.at(-1);
  assert.equal(xhr.method,'POST'); assert.equal(xhr.url,'http://192.168.1.5:8000/validate-image');
  assert.equal(xhr.body,body); assert.equal(xhr.didAbort,undefined);
  xhr.status=200; xhr.responseText='{"is_valid":true}'; xhr.onload();
  const response=await pending;
  assert.equal(response.ok,true); assert.equal(JSON.stringify(await response.json()),'{"is_valid":true}');
  assert.equal(response.headers.get('X-Test'),'value');
  controller.abort(); assert.equal(xhr.didAbort,undefined);
});

test('native XHR preserves FastAPI rejection details for the API error handler', async () => {
  const pending=nativeMultipartUpload('http://192.168.1.5:8000/check-plant-suitability',form(),new AbortController().signal);
  const xhr=sent.at(-1); xhr.status=422; xhr.responseText='{"detail":{"code":"non_plant_image","message":"Not a leaf"}}'; xhr.onload();
  const response=await pending;
  assert.equal(response.ok,false); assert.equal(response.status,422);
  assert.equal(JSON.stringify(await response.json()),'{"detail":{"code":"non_plant_image","message":"Not a leaf"}}');
});

test('network errors reject as network failures', async () => {
  const pending=nativeMultipartUpload('http://192.168.1.5:8000/predict',form(),new AbortController().signal);
  sent.at(-1).onerror();
  await assert.rejects(pending,error=>error.name==='TypeError' && error.message==='Network request failed');
});

test('caller cancellation aborts XHR and rejects with AbortError', async () => {
  const controller=new AbortController();
  const pending=nativeMultipartUpload('http://192.168.1.5:8000/validate-image',form(),controller.signal);
  const xhr=sent.at(-1); controller.abort();
  await assert.rejects(pending,error=>error.name==='AbortError');
  assert.equal(xhr.didAbort,true);
  xhr.onload?.(); // Late native completion cannot settle the request again.
});

test('a signal already aborted never starts a native request', async () => {
  const controller=new AbortController(); controller.abort();
  const count=sent.length;
  await assert.rejects(nativeMultipartUpload('http://192.168.1.5:8000/scan',form(),controller.signal),error=>error.name==='AbortError');
  const xhr=sent.at(-1);
  assert.equal(sent.length,count+1); assert.equal(xhr.method,undefined); assert.equal(xhr.body,undefined);
});

test('native multipart setup failures return a safe actionable error', async () => {
  class BrokenXHR extends XHR { send() { throw new Error('native internals'); } }
  const broken=loadTs('../src/nativeMultipartUpload.ts',{XMLHttpRequest:BrokenXHR});
  await assert.rejects(broken.nativeMultipartUpload('http://192.168.1.5:8000/scan',form(),new AbortController().signal),
    error=>error.name==='Error' && /Retake the photo/.test(error.message) && !/native internals/.test(error.message));
});
