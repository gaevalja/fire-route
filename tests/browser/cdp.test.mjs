import assert from 'node:assert/strict';
import {test} from 'node:test';
import {runInNewContext} from 'node:vm';
import {PipeMessages,until,navigatePage,waitForDocument,page} from './cdp.mjs';

test('CDP handles chunked/coalesced frames and out-of-order request IDs',async()=>{
  const sent=[];const p=new PipeMessages(s=>sent.push(JSON.parse(s.slice(0,-1))));
  const a=p.request('Page.enable'),b=p.request('Runtime.enable');
  p.receive('{"id":2,"result":{"ok":2}}\0{"id":');
  p.receive('1,"result":{"ok":1}}\0');
  assert.deepEqual(await a,{ok:1});assert.deepEqual(await b,{ok:2});assert.equal(sent.length,2);
});
test('CDP errors never include evaluated secret parameters',async()=>{
  const p=new PipeMessages(()=>{});const a=p.request('Runtime.evaluate',{expression:'PRIVATE_CODE'});
  p.receive('{"id":1,"error":{"message":"PRIVATE_CODE"}}\0');
  await assert.rejects(a,e=>!e.message.includes('PRIVATE_CODE')&&e.message.includes('Runtime.evaluate'));
});
test('browser close rejects in-flight requests',async()=>{
  const p=new PipeMessages(()=>{});const a=p.request('Page.enable');p.close();await assert.rejects(a,/browser exited/);
});
test('deadline and send failure release pending requests',async()=>{
  const p=new PipeMessages(()=>{});await assert.rejects(p.request('Page.enable',{},undefined,5),/timeout/);assert.equal(p.pending.size,0);
  const q=new PipeMessages(()=>{throw new Error('PRIVATE_CODE');});await assert.rejects(q.request('Page.enable'),/pipe unavailable/);
});
test('waits fail rather than fabricating a completed UI condition',async()=>{
  await assert.rejects(until(async()=>false,1),/condition/);
});
test('selected runtime events are routed without retaining secret frame payloads',()=>{
  const p=new PipeMessages(()=>{});let count=0;
  p.listeners.set('Page.screencastFrame',()=>count++);
  p.receive('{"method":"Page.screencastFrame","params":{"data":"PRIVATE_FRAME"}}\0');
  assert.equal(count,1);assert.equal(p.events.length,0);assert.equal(p.buffer,'');
});
test('initial page GET waits through connection refusal and does not emit any action request',async()=>{
  let attempts=0,time=0;const calls=[];
  const request=async(method,params)=>{calls.push({method,params});return ++attempts<3?{errorText:'net::ERR_CONNECTION_REFUSED'}:{};};
  const result=await navigatePage(request,'http://127.0.0.1:3001',{timeout:20,interval:5,now:()=>time,sleep:async ms=>{time+=ms;}});
  assert.deepEqual(result,{attempts:3});assert.equal(calls.length,3);
  assert.ok(calls.every(c=>c.method==='Page.navigate'&&c.params.url==='http://127.0.0.1:3001'));
});
test('certificate errors stop initial navigation immediately without verification bypass',async()=>{
  let calls=0;
  await assert.rejects(navigatePage(async()=>{calls++;return {errorText:'net::ERR_CERT_AUTHORITY_INVALID'};},'https://127.0.0.1:3443'),
    e=>e.code==='LOCAL_NAVIGATION_FAILED'&&e.networkError==='net::ERR_CERT_AUTHORITY_INVALID');
  assert.equal(calls,1);
});
test('unavailable page stops at a bounded deadline with a fixed network code',async()=>{
  let time=0,calls=0;
  await assert.rejects(navigatePage(async()=>{calls++;return {errorText:'net::ERR_CONNECTION_REFUSED'};},'http://127.0.0.1:3001',
    {timeout:10,interval:5,now:()=>time,sleep:async ms=>{time+=ms;}}),
    e=>e.code==='LOCAL_NAVIGATION_FAILED'&&e.networkError==='net::ERR_CONNECTION_REFUSED'&&e.attempts===3);
  assert.equal(calls,3);
});
test('arbitrary navigation error text never enters thrown diagnostics',async()=>{
  await assert.rejects(navigatePage(async()=>({errorText:'PRIVATE_CODE_OR_URL'}),'http://127.0.0.1:3001'),
    e=>e.networkError==='UNAVAILABLE'&&!e.message.includes('PRIVATE_CODE'));
});

// Synthetic parser/CDP fixtures, not an executed Chrome or CSE result.
test('document wait rejects about:blank and parser-created forms until the target module has finished',async()=>{
  let time=0,index=0;const requests=[];
  const states=[
    {location:{href:'about:blank'},document:{readyState:'complete'}},
    {location:{href:'http://127.0.0.1:3001/'},document:{readyState:'loading'}},
    {location:{href:'http://127.0.0.1:3001/'},document:{readyState:'interactive'}},
    {location:{href:'http://127.0.0.1:3001/'},document:{readyState:'complete'}},
  ];
  await waitForDocument(async(method,params)=>{
    requests.push({method,params});const value=runInNewContext(params.expression,states[index++]);
    return {result:{value}};
  },'http://127.0.0.1:3001',{timeout:30,interval:5,now:()=>time,sleep:async ms=>{time+=ms;}});
  assert.equal(index,4);assert.equal(time,15);
  assert.ok(requests.every(r=>r.method==='Runtime.evaluate'&&!r.params.expression.includes('requestSubmit')));
});
test('document wait is bounded and does not treat a different complete document as ready',async()=>{
  let time=0,calls=0;
  await assert.rejects(waitForDocument(async(method,params)=>{
    calls++;return {result:{value:runInNewContext(params.expression,
      {location:{href:'http://127.0.0.1:3001/?'},document:{readyState:'complete'}})}};
  },'http://127.0.0.1:3001',{timeout:10,interval:5,now:()=>time,sleep:async ms=>{time+=ms;}}),
    e=>e.code==='DOCUMENT_NOT_READY');
  assert.equal(calls,3);
});
test('document wait retains evaluation failures without leaking or swallowing their payload',async()=>{
  let calls=0;
  await assert.rejects(waitForDocument(async()=>{calls++;return {exceptionDetails:{text:'PRIVATE_VALUE'}};},
    'http://127.0.0.1:3001'),e=>e.message==='Browser page evaluation failed'&&!e.message.includes('PRIVATE_VALUE'));
  assert.equal(calls,1);
});
test('each new page waits for the destination document before exposing its action evaluator',async()=>{
  const methods=[];
  const browser={protocol:{request:async(method,params,sessionId)=>{
    methods.push(method);
    if(method==='Target.createBrowserContext')return {browserContextId:'fixture-context'};
    if(method==='Target.createTarget')return {targetId:'fixture-target'};
    if(method==='Target.attachToTarget')return {sessionId:'fixture-session'};
    assert.equal(sessionId,'fixture-session');
    if(method==='Runtime.evaluate'){
      assert.ok(params.expression.includes("document.readyState==='complete'"));
      return {result:{value:true}};
    }
    return {};
  }}};
  const p=await page(browser,'http://127.0.0.1:3001');
  assert.equal(p.sessionId,'fixture-session');
  assert.deepEqual(methods,['Target.createBrowserContext','Target.createTarget','Target.attachToTarget',
    'Page.enable','Runtime.enable','Page.navigate','Runtime.evaluate']);
});
