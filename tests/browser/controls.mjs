// Wait for the rendered control, independently of backend readiness.
// No click retry after dispatch: a missing action response may be ambiguous.
export class BrowserCheckError extends Error {
  constructor(code, details={}) {super(code);this.name='BrowserCheckError';this.code=code;this.details=details;}
}

export async function submitLogin(page,role,accessCode) {
  if(!['resident','responder'].includes(role)||typeof accessCode!=='string'||!accessCode)
    throw new BrowserCheckError('LOGIN_INPUT_INVALID');
  const result=await page.evaluate(`(()=>{
    const form=document.querySelector('#login-form'),role=document.querySelector('#role'),code=document.querySelector('#code');
    if(!form||!role||!code)return 'LOGIN_FORM_NOT_READY';
    role.value=${JSON.stringify(role)};code.value=${JSON.stringify(accessCode)};
    // Registered after the app's listener. Block native GET navigation if the
    // app never called preventDefault; do not retry a possibly sent login POST.
    let handled=false;
    const guard=event=>{handled=event.defaultPrevented;if(!handled)event.preventDefault();};
    form.addEventListener('submit',guard,{once:true});
    try{
      if(!form.checkValidity())return 'LOGIN_FORM_INVALID';
      form.requestSubmit();return handled?'HANDLED':'LOGIN_HANDLER_NOT_READY';
    }finally{form.removeEventListener('submit',guard);if(!handled)code.value='';}
  })()`);
  if(result!=='HANDLED')throw new BrowserCheckError(
    ['LOGIN_FORM_NOT_READY','LOGIN_FORM_INVALID','LOGIN_HANDLER_NOT_READY'].includes(result)?result:'LOGIN_HANDLER_NOT_READY');
}

export async function clickControl(page,selector,{timeout=30000,interval=100,onState=()=>{},
  now=()=>performance.now(),sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms))}={}) {
  const deadline=now()+timeout;
  let state={present:false};
  while(true) {
    state=await page.evaluate(`(()=>{
      const e=document.querySelector(${JSON.stringify(selector)});
      if(!e)return {present:false};
      const visible=e.getClientRects().length>0&&!e.closest('[hidden]');
      const disabled=!!e.disabled||e.matches(':disabled')||e.getAttribute('aria-disabled')==='true';
      if(visible)e.scrollIntoView({block:'center',inline:'nearest'});
      const r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2;
      const inViewport=r.width>0&&r.height>0&&x>=0&&y>=0&&x<innerWidth&&y<innerHeight;
      const hit=inViewport?document.elementFromPoint(x,y):null;
      return {present:true,visible,disabled,inViewport,hitTarget:!!hit&&(hit===e||e.contains(hit)),x,y};
    })()`);
    onState(state);
    if(state.present&&state.visible&&!state.disabled&&state.inViewport&&state.hitTarget
        &&Number.isFinite(state.x)&&Number.isFinite(state.y))break;
    if(now()>=deadline)throw new BrowserCheckError('CONTROL_NOT_READY',safeControlState(state));
    await sleep(Math.min(interval,Math.max(0,deadline-now())));
  }
  await page.request('Input.dispatchMouseEvent',{type:'mousePressed',x:state.x,y:state.y,button:'left',clickCount:1});
  await page.request('Input.dispatchMouseEvent',{type:'mouseReleased',x:state.x,y:state.y,button:'left',clickCount:1});
}

export function safeControlState(state) {
  return Object.fromEntries(['present','visible','disabled','inViewport','hitTarget']
    .filter(key=>typeof state?.[key]==='boolean').map(key=>[key,state[key]]));
}

export function safeFailure(error) {
  if(error?.code==='DOCUMENT_NOT_READY')return {code:'DOCUMENT_NOT_READY'};
  if(error?.code==='LOCAL_NAVIGATION_FAILED')return {code:'LOCAL_NAVIGATION_FAILED',
    networkError:/^net::ERR_[A-Z0-9_]+$/.test(error.networkError)?error.networkError:'UNAVAILABLE',
    ...(Number.isInteger(error.attempts)&&error.attempts>0?{attempts:error.attempts}:{})};
  const code=error instanceof BrowserCheckError?error.code:
    error?.message?.startsWith('Check failed: ')?'ASSERTION_FAILED':
    error?.message==='Browser condition did not complete within budget'?'CONDITION_TIMEOUT':
    error?.message==='Browser page evaluation failed'?'PAGE_EVALUATION_FAILED':
    error?.message?.startsWith('CDP timeout: ')?'CDP_TIMEOUT':
    error?.message?.startsWith('CDP rejected: ')?'CDP_REJECTED':
    error?.message?.startsWith('Chrome startup unavailable')?'CHROME_STARTUP_UNAVAILABLE':'BROWSER_OPERATION_FAILED';
  // Never serialize raw exceptionDetails, evaluate expressions or arbitrary messages.
  return {code,...(error instanceof BrowserCheckError?{control:safeControlState(error.details)}:{})};
}

export async function renderedState(page) {
  return page.evaluate(`(()=>{
    const ids=['app','login','controls','private','person'];
    const elements=Object.fromEntries(ids.map(id=>{const e=document.getElementById(id);return [id,e?{
      hidden:!!e.hidden,visible:e.getClientRects().length>0,disabled:!!e.disabled,
      ...(id==='person'?{optionCount:e.options.length}:{})}:null];}));
    const controls=Array.from(document.querySelectorAll('[data-action]')).map(e=>({
      action:['step','advance_30','resume','pause','stop_display_c','reset'].includes(e.dataset.action)?e.dataset.action:'UNKNOWN',
      disabled:!!e.disabled,visible:e.getClientRects().length>0}));
    return {readyState:document.readyState,elements,controls};
  })()`);
}
