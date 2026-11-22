// Browser/CDP fixtures only; these are not real DOM/CSE integration results.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {runInNewContext} from 'node:vm';
import {BrowserCheckError,clickControl,submitLogin,safeControlState,safeFailure} from './controls.mjs';

const ready={present:true,visible:true,disabled:false,inViewport:true,hitTarget:true,x:200,y:100};
function fixture(states) {
  const requests=[];let index=0,time=0;
  const page={evaluate:async()=>states[Math.min(index++,states.length-1)],
    request:async(method,params)=>{requests.push({method,params});}};
  return {page,requests,clock:{timeout:30,interval:5,now:()=>time,sleep:async ms=>{time+=ms;}}};
}

test('backend ready does not bypass a disabled rendered button; dispatch once after UI polling catches up',async()=>{
  const f=fixture([{...ready,disabled:true},{...ready,disabled:true},ready]);let samples=0;
  await clickControl(f.page,'[data-action="reset"]',{...f.clock,onState:()=>samples++});
  assert.equal(samples,3);assert.deepEqual(f.requests.map(r=>r.params.type),['mousePressed','mouseReleased']);
});
test('missing, hidden or covered controls are not clicked',async()=>{
  for(const state of [{present:false},{...ready,visible:false},{...ready,hitTarget:false},{...ready,inViewport:false}]){
    const f=fixture([state]);await assert.rejects(clickControl(f.page,'button',f.clock),e=>e.code==='CONTROL_NOT_READY');
    assert.deepEqual(f.requests,[]);
  }
});
test('non-finite geometry cannot create an input command',async()=>{
  const f=fixture([{...ready,x:NaN}]);await assert.rejects(clickControl(f.page,'button',f.clock),/CONTROL_NOT_READY/);
  assert.deepEqual(f.requests,[]);
});
test('an uncertain mouse dispatch is not automatically replayed',async()=>{
  const f=fixture([ready]);f.page.request=async()=>{f.requests.push('attempt');throw new Error('PIPE_LOST');};
  await assert.rejects(clickControl(f.page,'button',f.clock),/PIPE_LOST/);assert.equal(f.requests.length,1);
});
test('safe diagnostics retain only boolean control state and fixed error codes',()=>{
  assert.deepEqual(safeControlState({...ready,password:'PRIVATE',value:'PRIVATE'}),
    {present:true,visible:true,disabled:false,inViewport:true,hitTarget:true});
  assert.deepEqual(safeFailure(new Error('PRIVATE_CODE')), {code:'BROWSER_OPERATION_FAILED'});
  assert.equal(safeFailure(new Error('Browser condition did not complete within budget')).code,'CONDITION_TIMEOUT');
  const failure=safeFailure(new BrowserCheckError('CONTROL_NOT_READY',{disabled:true,password:'PRIVATE'}));
  assert.deepEqual(failure,{code:'CONTROL_NOT_READY',control:{disabled:true}});
  assert.deepEqual(safeFailure({code:'LOCAL_NAVIGATION_FAILED',networkError:'net::ERR_CONNECTION_REFUSED',attempts:3}),
    {code:'LOCAL_NAVIGATION_FAILED',networkError:'net::ERR_CONNECTION_REFUSED',attempts:3});
  assert.deepEqual(safeFailure({code:'LOCAL_NAVIGATION_FAILED',networkError:'PRIVATE_VALUE'}),
    {code:'LOCAL_NAVIGATION_FAILED',networkError:'UNAVAILABLE'});
  assert.deepEqual(safeFailure({code:'DOCUMENT_NOT_READY',message:'PRIVATE_VALUE'}),{code:'DOCUMENT_NOT_READY'});
});

function loginFixture({installed=true,valid=true}={}) {
  const listeners=[],counts={posts:0,nativeGets:0,submits:0};
  const code={value:''},role={value:''};
  if(installed)listeners.push(event=>{event.preventDefault();counts.posts++;});
  const form={
    addEventListener:(name,listener)=>listeners.push(listener),
    removeEventListener:(name,listener)=>{const i=listeners.indexOf(listener);if(i>=0)listeners.splice(i,1);},
    checkValidity:()=>valid,
    requestSubmit:()=>{
      counts.submits++;
      const event={defaultPrevented:false,preventDefault(){this.defaultPrevented=true;}};
      for(const listener of [...listeners])listener(event);
      if(!event.defaultPrevented)counts.nativeGets++;
    },
  };
  const document={querySelector:selector=>({'#login-form':form,'#role':role,'#code':code}[selector]??null)};
  return {page:{evaluate:async expression=>runInNewContext(expression,{document})},counts,code,role,listeners};
}
test('login submits once through the installed application handler and removes its temporary guard',async()=>{
  const f=loginFixture();await submitLogin(f.page,'resident','FIXTURE_ONLY');
  assert.deepEqual(f.counts,{posts:1,nativeGets:0,submits:1});
  assert.equal(f.role.value,'resident');assert.equal(f.listeners.length,1);
});
test('missing deferred login listener fails without native GET navigation, retry or a retained password',async()=>{
  const f=loginFixture({installed:false});
  await assert.rejects(submitLogin(f.page,'resident','FIXTURE_ONLY'),e=>e.code==='LOGIN_HANDLER_NOT_READY');
  assert.deepEqual(f.counts,{posts:0,nativeGets:0,submits:1});
  assert.equal(f.code.value,'');assert.equal(f.listeners.length,0);
});
test('invalid form sends no login and removes its password and temporary listener',async()=>{
  const f=loginFixture({valid:false});
  await assert.rejects(submitLogin(f.page,'resident','FIXTURE_ONLY'),e=>e.code==='LOGIN_FORM_INVALID');
  assert.deepEqual(f.counts,{posts:0,nativeGets:0,submits:0});
  assert.equal(f.code.value,'');assert.equal(f.listeners.length,1);
});
test('missing form and ambiguous login evaluation fail without replay or secret diagnostics',async()=>{
  const empty={evaluate:async expression=>runInNewContext(expression,{document:{querySelector:()=>null}})};
  await assert.rejects(submitLogin(empty,'resident','FIXTURE_ONLY'),e=>e.code==='LOGIN_FORM_NOT_READY');
  let calls=0;
  const broken={evaluate:async()=>{calls++;throw new Error('CDP rejected: Runtime.evaluate');}};
  await assert.rejects(submitLogin(broken,'resident','FIXTURE_ONLY'),/CDP rejected/);
  assert.equal(calls,1);
  const failure=safeFailure(new BrowserCheckError('LOGIN_HANDLER_NOT_READY'));
  assert.equal(failure.code,'LOGIN_HANDLER_NOT_READY');assert.ok(!JSON.stringify(failure).includes('FIXTURE_ONLY'));
});
