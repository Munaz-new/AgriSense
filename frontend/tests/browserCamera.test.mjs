// Exercise the real browser camera controller with DOM/media doubles, not hardware.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import ts from 'typescript';

const compiled=ts.transpileModule(readFileSync(new URL('../src/browserCamera.ts',import.meta.url),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText;
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function browser(options={}) {
  const elements=[],timers=new Map();let requests=0,stops=0,draws=0,encodes=0,focusRestored=0;
  let constraints,encode;
  const track={onended:null,stop(){stops++;}};
  const stream={getTracks:()=>[track]};
  const window=new EventTarget();window.isSecureContext=options.secure!==false;
  const document=new EventTarget();document.hidden=false;
  document.activeElement={focus(){focusRestored++;}};
  document.body={append(node){node.attached=true;}};
  document.createElement=tag=>{
    const node={tag,style:{},attributes:{},children:[],textContent:'',disabled:false,
      append(...children){this.children.push(...children);},setAttribute(key,value){this.attributes[key]=value;},
      showModal(){this.open=true;},close(){this.open=false;},remove(){this.attached=false;},focus(){},
    };
    if(tag==='video') Object.assign(node,{videoWidth:options.width??1600,videoHeight:1200,readyState:options.ready===false?0:2,
      play:async()=>{if(options.playError)throw options.playError;}});
    if(tag==='canvas') Object.assign(node,{getContext:()=>options.noCanvas?null:{drawImage(){draws++;}},
      toBlob(callback,type){encodes++;assert.equal(type,'image/jpeg');
        encode=()=>callback(options.empty?null:new Blob(['camera fixture'],{type}));
        if(!options.delayedEncode)encode();
      }});
    elements.push(node);return node;
  };
  const exports={};
  runInNewContext(compiled,{exports,window,document,Error,URL,setTimeout:fn=>{const id={};timers.set(id,fn);return id;},
    clearTimeout:id=>timers.delete(id),navigator:{mediaDevices:options.unsupported?undefined:{getUserMedia:async input=>{
      requests++;constraints=input;
      if(options.error)throw options.error;
      return options.acquire?await options.acquire():stream;
    }}},
  });
  const controller=new AbortController();
  return {start:()=>exports.captureBrowserPhoto(controller.signal),controller,window,document,elements,track,stream,
    element:tag=>elements.find(node=>node.tag===tag),button:text=>elements.find(node=>node.textContent===text),
    metrics:()=>({requests,stops,draws,encodes,focusRestored,constraints}),
    encode:()=>encode(),timeout:()=>[...timers.values()].forEach(fn=>fn()),timers};
}

test('live browser capture requests video only, requires explicit capture, returns JPEG and releases camera',async()=>{
  const b=browser();const result=b.start();await tick();
  assert.equal(b.metrics().constraints.audio,false);
  assert.equal(b.metrics().constraints.video.facingMode.ideal,'environment');
  assert.equal(b.element('video').srcObject,b.stream);assert.equal(b.element('dialog').open,true);
  assert.equal(b.metrics().draws,0);assert.equal(b.button('Capture photo').disabled,false);
  b.button('Capture photo').onclick();b.button('Capture photo').onclick();
  const photo=await result;assert.equal(photo.canceled,false);assert.equal(photo.assets[0].mimeType,'image/jpeg');
  assert.equal(photo.assets[0].width,1600);assert.equal(photo.assets[0].height,1200);
  assert.equal(await (await fetch(photo.assets[0].uri)).text(),'camera fixture');URL.revokeObjectURL(photo.assets[0].uri);
  assert.equal(b.metrics().stops,1);assert.equal(b.metrics().encodes,1);assert.equal(b.metrics().focusRestored,1);
  assert.equal(b.element('video').srcObject,null);assert.equal(b.element('dialog').attached,false);assert.equal(b.timers.size,0);
});

for(const [options,message] of [[{secure:false},/HTTPS or localhost/],[{unsupported:true},/does not support live/],
  [{error:{name:'NotAllowedError'}},/denied or blocked/],[{error:{name:'NotFoundError'}},/No usable camera/],
  [{error:{name:'NotReadableError'}},/unavailable or in use/],[{playError:{name:'NotAllowedError'}},/denied or blocked/]]) {
  test(`browser camera failure is actionable: ${JSON.stringify(options)}`,async()=>{
    const b=browser(options);await assert.rejects(b.start(),message);
    assert.ok(!b.element('dialog')?.attached);assert.equal(b.timers.size,0);
    if(options.playError)assert.equal(b.metrics().stops,1);
    if(options.secure===false||options.unsupported)assert.equal(b.metrics().requests,0);
  });
}

for(const action of ['cancel','escape','abort','pagehide','popstate','hidden']) {
  test(`${action} closes browser preview and stops the stream`,async()=>{
    const b=browser();const pending=b.start();await tick();
    if(action==='cancel')b.button('Cancel camera').onclick();
    if(action==='escape')b.element('dialog').oncancel({preventDefault(){}});
    if(action==='abort')b.controller.abort();
    if(action==='pagehide'||action==='popstate')b.window.dispatchEvent(new Event(action));
    if(action==='hidden'){b.document.hidden=true;b.document.dispatchEvent(new Event('visibilitychange'));}
    assert.equal((await pending).canceled,true);assert.equal(b.metrics().stops,1);
    assert.equal(b.element('dialog').attached,false);assert.equal(b.timers.size,0);
    b.window.dispatchEvent(new Event('pagehide'));assert.equal(b.metrics().stops,1);
  });
}

test('permission granted after cancellation stops late stream without reopening preview',async()=>{
  let grant;const b=browser({acquire:()=>new Promise(resolve=>{grant=resolve;})});
  const pending=b.start();b.button('Cancel camera').onclick();assert.equal((await pending).canceled,true);
  grant(b.stream);await tick();assert.equal(b.metrics().stops,1);assert.equal(b.element('dialog').attached,false);
  assert.equal(b.element('video').srcObject,null);
});

test('capture stops hardware before asynchronous encoding; cancel ignores late encoded photo',async()=>{
  const b=browser({delayedEncode:true});const pending=b.start();await tick();
  b.button('Capture photo').onclick();assert.equal(b.metrics().stops,1);
  b.controller.abort();assert.equal((await pending).canceled,true);b.encode();assert.equal(b.metrics().stops,1);
});

for(const [options,message] of [[{empty:true},/empty photo/],[{noCanvas:true},/could not capture/],[{width:100},/too small/]]) {
  test(`invalid captured photo rejects and releases camera: ${JSON.stringify(options)}`,async()=>{
    const b=browser(options);const pending=b.start();const rejection=assert.rejects(pending,message);await tick();
    b.button('Capture photo').onclick();await rejection;assert.equal(b.metrics().stops,1);assert.equal(b.timers.size,0);
  });
}

test('camera track ending reports unavailable and clears preview',async()=>{
  const b=browser();const pending=b.start();const rejection=assert.rejects(pending,/unavailable/);await tick();
  b.track.onended();await rejection;assert.equal(b.metrics().stops,1);
});

test('camera readiness and photo encoding have bounded waits with cleanup',async()=>{
  for(const ready of [false,true]) {
    const b=browser({ready,delayedEncode:true});const pending=b.start();
    const rejection=assert.rejects(pending,ready?/took too long/:/preview did not start/);await tick();
    if(ready)b.button('Capture photo').onclick();else assert.equal(b.button('Capture photo').disabled,true);
    b.timeout();await rejection;assert.equal(b.metrics().stops,1);assert.equal(b.timers.size,0);
  }
});
