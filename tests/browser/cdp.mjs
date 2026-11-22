// Minimal CDP pipe driver using Node built-ins. No shared browser/profile/port.
import {spawn} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {prepareFonts} from './fonts.mjs';

export class PipeMessages {
  constructor(send) {this.send=send;this.id=0;this.pending=new Map();this.buffer='';this.events=[];this.listeners=new Map();}
  request(method,params={},sessionId,timeout=15000) {
    const id=++this.id;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error(`CDP timeout: ${method}`));},timeout);
      this.pending.set(id,{resolve,reject,timer,method});
      try {this.send(JSON.stringify({id,method,params,...(sessionId?{sessionId}:{})})+'\0');}
      catch {clearTimeout(timer);this.pending.delete(id);reject(new Error(`CDP pipe unavailable: ${method}`));}
    });
  }
  receive(chunk) {
    this.buffer+=chunk;
    if(this.buffer.length>16*1024*1024){this.close();throw new Error('CDP frame exceeds limit');}
    let index;
    while((index=this.buffer.indexOf('\0'))>=0) {
      const frame=this.buffer.slice(0,index);this.buffer=this.buffer.slice(index+1);
      if(!frame)continue;
      const message=JSON.parse(frame),pending=this.pending.get(message.id);
      if(pending){this.pending.delete(message.id);clearTimeout(pending.timer);
        if(message.error)pending.reject(new Error(`CDP rejected: ${pending.method}`));else pending.resolve(message.result);}
      else if(message.method==='Runtime.exceptionThrown')this.events.push({method:message.method,sessionId:message.sessionId});
      if(message.method&&this.listeners.has(message.method))this.listeners.get(message.method)(message);
    }
  }
  close() {for(const p of this.pending.values()){clearTimeout(p.timer);p.reject(new Error('CDP browser exited'));}this.pending.clear();}
}

export async function launchChrome({trustedSPKI}={}) {
  const profile=await mkdtemp(join(tmpdir(),'fire-route-browser-'));
  let fonts;
  try{fonts=await prepareFonts(profile);}catch(error){await rm(profile,{recursive:true,force:true});throw error;}
  const chrome=process.env.CHROME_BIN||'google-chrome';
  // Preserve Chrome sandbox; there is deliberately no --no-sandbox option.
  if(trustedSPKI && !/^[A-Za-z0-9+/]{43}=$/.test(trustedSPKI))throw new Error('Invalid local certificate SPKI');
  const child=spawn(chrome,['--headless=new','--remote-debugging-pipe',`--user-data-dir=${profile}`,
    '--no-first-run','--no-default-browser-check','--disable-background-networking',
    '--disable-sync','--disable-component-update',...(trustedSPKI?[`--ignore-certificate-errors-spki-list=${trustedSPKI}`]:[]),'about:blank'],
    {stdio:['ignore','ignore','pipe','pipe','pipe'],env:{...process.env,...fonts.environment,XDG_CONFIG_HOME:profile,XDG_CACHE_HOME:profile}});
  let startupFailure=false;
  child.on('error',()=>{startupFailure=true;protocol.close();});
  const protocol=new PipeMessages(data=>child.stdio[3].write(data));
  for(const stream of [child.stdio[3],child.stdio[4]])stream.on('error',()=>{startupFailure=true;protocol.close();});
  child.stdio[4].setEncoding('utf8');
  child.stdio[4].on('data',data=>{try{protocol.receive(data);}catch{startupFailure=true;protocol.close();}});
  child.on('exit',()=>protocol.close());
  // Consume but never log browser stderr, URLs, cookies or evaluated login text.
  child.stderr.resume();
  const close=async()=>{
    try{if(child.exitCode===null&&!startupFailure)await protocol.request('Browser.close',{},undefined,2000);}catch{}
    if(child.exitCode===null)child.kill('SIGTERM');
    protocol.close();await rm(profile,{recursive:true,force:true,maxRetries:3});
  };
  try {const version=await protocol.request('Browser.getVersion');return {protocol,version,close,fontConfiguration:fonts.mode};}
  catch{await close();throw new Error('Chrome startup unavailable; install Chrome/Chromium and enable its sandbox');}
}

export async function page(browser,url) {
  const context=await browser.protocol.request('Target.createBrowserContext');
  const {targetId}=await browser.protocol.request('Target.createTarget',{url:'about:blank',browserContextId:context.browserContextId});
  const {sessionId}=await browser.protocol.request('Target.attachToTarget',{targetId,flatten:true});
  const request=(method,params={})=>browser.protocol.request(method,params,sessionId);
  await request('Page.enable');await request('Runtime.enable');
  const evaluate=async(expression)=>{
    const r=await request('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(r.exceptionDetails)throw new Error('Browser page evaluation failed');
    return r.result.value;
  };
  const navigation=await navigatePage(request,url);
  // Page.navigate can finish while HTML is still being parsed. A parser-created
  // form is not proof that its deferred module has installed the submit handler.
  await waitForDocument(request,url);
  return {request,evaluate,sessionId,navigation};
}

export async function waitForDocument(request,url,{timeout=30000,interval=100,
  now=()=>performance.now(),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))}={}) {
  const expected=new URL(url).href,deadline=now()+timeout;
  const expression=`location.href===${JSON.stringify(expected)} && document.readyState==='complete'`;
  while(true) {
    // Only poll this read-only predicate, never credentials or an action.
    const result=await request('Runtime.evaluate',{expression,returnByValue:true});
    if(result.exceptionDetails)throw new Error('Browser page evaluation failed');
    if(result.result?.value===true)return;
    if(now()>=deadline){const error=new Error('Browser document did not become ready');error.code='DOCUMENT_NOT_READY';throw error;}
    await sleep(Math.min(interval,Math.max(0,deadline-now())));
  }
}

export async function navigatePage(request,url,{timeout=15000,interval=250,
  now=()=>performance.now(),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))}={}) {
  // This runs only on the initial page GET, before credentials/actions exist.
  // Do not retry certificate/authentication errors or any subsequent action.
  const transient=new Set(['net::ERR_CONNECTION_REFUSED','net::ERR_CONNECTION_RESET','net::ERR_EMPTY_RESPONSE']);
  const deadline=now()+timeout;let attempts=0;
  while(true) {
    const navigation=await request('Page.navigate',{url});attempts++;
    if(!navigation.errorText)return {attempts};
    const networkError=/^net::ERR_[A-Z0-9_]+$/.test(navigation.errorText)?navigation.errorText:'UNAVAILABLE';
    if(!transient.has(networkError)||now()>=deadline) {
      const error=new Error('Local dashboard navigation failed');
      error.code='LOCAL_NAVIGATION_FAILED';error.networkError=networkError;error.attempts=attempts;
      throw error;
    }
    await sleep(Math.min(interval,Math.max(0,deadline-now())));
  }
}

export async function until(fn,timeout=90000) {
  const end=Date.now()+timeout;
  while(Date.now()<end){if(await fn())return;await new Promise(r=>setTimeout(r,250));}
  throw new Error('Browser condition did not complete within budget');
}
