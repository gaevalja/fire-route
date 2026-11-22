// Real rendered dashboard against the actual running local CSE-backed app.
// Reads private codes in memory; never exports login bodies, cookies or traces.
import {readFile,mkdir,writeFile,stat} from 'node:fs/promises';
import {randomUUID,createHash,X509Certificate} from 'node:crypto';
import {resolve,join} from 'node:path';
import {launchChrome,page,until} from './cdp.mjs';
import {record} from './record.mjs';
import {clickControl,submitLogin,renderedState,safeControlState,safeFailure} from './controls.mjs';

const root=resolve(import.meta.dirname,'../..');
const run=new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d+Z$/,'Z').replace('T','-')+'-'+randomUUID().slice(0,8);
const directory=join(root,'evidence',run);await mkdir(directory,{recursive:true});
const checks={};let browser,phase='PREFLIGHT',started=false,finishRecording,responder,activePage,lastControl;
let pageRole='responder';
const summary={test:'LOCAL_RENDERED_BROWSER',state:'NOT_RUN',Hosted:'NOT_CONTACTED',MEC:'unavailable',
  input:'SYNTHETIC',CSE:'REQUIRES_CORRELATION_WITH_APP_RUN',video:'NOT_RECORDED'};
const check=(name,result)=>{checks[name]=Boolean(result);if(!result)throw new Error(`Check failed: ${name}`);};
const secure=process.argv.includes('--https');
const portIndex=process.argv.indexOf('--port');
const port=portIndex>=0?Number(process.argv[portIndex+1]):secure?3443:3001;
if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Invalid loopback browser port');
const origin=`${secure?'https':'http'}://127.0.0.1:${port}`; // No remote mutating targets.
const save=async(name,data)=>writeFile(join(directory,name),JSON.stringify(data,null,2)+'\n');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
try {
  // Reject unprotected access-code files instead of saving their contents.
  const codePath=join(root,'.runtime/access-codes.json');
  const info=await stat(codePath);
  if(info.mode&0o077)throw new Error('Private access-code file permissions required');
  const codes=JSON.parse(await readFile(codePath,'utf8'));
  if(!codes.resident||!codes.responder)throw new Error('Run make access-codes first');
  let trustedSPKI;
  if(secure){const cert=new X509Certificate(await readFile(join(root,'.runtime/tls/server.crt')));
    trustedSPKI=createHash('sha256').update(cert.publicKey.export({type:'spki',format:'der'})).digest('base64');}
  browser=await launchChrome({trustedSPKI});summary.browser=browser.version.product;
  summary.font_configuration=browser.fontConfiguration;
  summary.transport=secure?'HTTPS_LOCAL_CERTIFICATE_PINNED_IN_TEST_PROFILE':'HTTP_LOOPBACK_DEV';
  phase='NAVIGATION';
  responder=await page(browser,origin);
  activePage=responder;
  summary.navigation_attempts=responder.navigation.attempts;
  started=true;phase='PAGE_READY';
  await until(()=>responder.evaluate('!!document.querySelector("#login-form")'));
  phase='ROLE_LOGIN';
  check('interactive_fields_have_accessible_labels',await responder.evaluate('["role","code","floor","mode","person"].every(id=>document.getElementById(id).labels.length>0)'));
  await responder.evaluate('document.querySelector("#role").focus();true');
  await responder.request('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,nativeVirtualKeyCode:9});
  await responder.request('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,nativeVirtualKeyCode:9});
  check('keyboard_reaches_password_input',await responder.evaluate('document.activeElement.id==="code"'));
  const login=async(p,role)=>{
    await submitLogin(p,role,codes[role]);
    await until(()=>p.evaluate('document.querySelector("#login").hidden && !document.querySelector("#app").hidden'));
    check(role+'_password_field_cleared',await p.evaluate('document.querySelector("#code").value === ""'));
  };
  const api=async(p,path)=>p.evaluate(`fetch(${JSON.stringify(path)},{cache:'no-store'}).then(async r=>({status:r.status,body:await r.json()}))`);
  const click=async(p,selector)=>{
    lastControl=undefined;
    await clickControl(p,selector,{onState:state=>{lastControl=safeControlState(state);}});
  };
  const ready=async()=>until(async()=>{const r=await api(responder,'/api/v1/status');return r.status===200&&r.body.state==='READY'&&!r.body.busy;},120000);
  await login(responder,'responder');await ready();
  if(process.argv.includes('--record'))finishRecording=await record(browser,responder,directory);
  check('responder_controls_visible',await responder.evaluate('!document.querySelector("#controls").hidden && !document.querySelector("#private").hidden'));
  phase='NEW_INCIDENT';const before=(await api(responder,'/api/v1/status')).body.incident_id;
  summary.before_incident_id=before;
  await click(responder,'[data-action="reset"]');
  await until(async()=>{const r=await api(responder,'/api/v1/status');return r.body.incident_id&&r.body.incident_id!==before&&!r.body.busy;},120000);
  await ready();await delay(1800);
  const initial=(await api(responder,'/api/v1/status')).body;
  summary.incident_id=initial.incident_id;
  check('reset_created_new_paused_incident',initial.paused&&initial.incident_id!==before);
  check('both_modes_and_170_residents_rendered',await responder.evaluate('!document.querySelector("#moving-option").hidden && document.querySelector("#person").options.length===170 && !document.querySelector("#person").disabled'));
  await responder.evaluate('document.querySelector("#mode").value="moving";document.querySelector("#mode").dispatchEvent(new Event("change"));document.querySelector("#person").selectedIndex=12;document.querySelector("#person").dispatchEvent(new Event("change"));true');
  const selected=await responder.evaluate('document.querySelector("#person").value');
  await delay(3500);
  check('selection_survives_polling',await responder.evaluate(`document.querySelector('#person').value===${JSON.stringify(selected)}`));
  check('moving_person_drawn_in_real_SVG',await responder.evaluate('document.querySelectorAll("#map circle.person").length===1'));
  phase='ADVANCE_AND_PLAYBACK';
  await click(responder,'[data-action="advance_30"]');await ready();
  await until(()=>responder.evaluate('document.querySelector("#clock").textContent.includes("30")'),120000);
  const view=(await api(responder,`/api/v1/incidents/${initial.incident_id}/responder`)).body;
  check('thirty_seconds_committed_and_population_conserved',view.simulation_second===30&&view.population.total===view.population.evacuated+view.population.remaining);
  check('three_device_ACKs_rendered',await responder.evaluate('document.querySelector("#acks").textContent.startsWith("3 / 3")'));
  await click(responder,'[data-action="resume"]');
  await until(async()=>!(await api(responder,'/api/v1/status')).body.paused);
  await delay(2500);
  await until(()=>responder.evaluate('!document.querySelector("[data-action=pause]").disabled'));
  await click(responder,'[data-action="pause"]');
  await until(async()=>(await api(responder,'/api/v1/status')).body.paused);await ready();
  check('pause_stops_automatic_playback',(await api(responder,'/api/v1/status')).body.paused);
  const screen=async(p,name)=>{
    await p.evaluate('document.querySelector("#app").scrollIntoView({block:"start"});true');
    const shot=await p.request('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(directory,name),Buffer.from(shot.data,'base64'));
  };
  await screen(responder,'responder.png');
  phase='RESIDENT_NAVIGATION';pageRole='resident';lastControl=undefined;activePage=undefined;
  const resident=await page(browser,origin);activePage=resident;
  summary.resident_navigation_attempts=resident.navigation.attempts;
  phase='RESIDENT_LOGIN';await until(()=>resident.evaluate('!!document.querySelector("#login-form")'));
  await login(resident,'resident');await delay(1800);
  phase='RESIDENT_ISOLATION';
  check('resident_private_controls_hidden',await resident.evaluate('document.querySelector("#controls").hidden&&document.querySelector("#private").hidden&&document.querySelector("#moving-option").hidden'));
  const forbidden=await api(resident,`/api/v1/incidents/${initial.incident_id}/snapshot`);
  check('resident_private_snapshot_actually_403',forbidden.status===403);
  const residentView=await api(resident,`/api/v1/incidents/${initial.incident_id}/resident`);
  check('resident_payload_excludes_private_people',!('residents' in residentView.body)&&!('population' in residentView.body)&&!('occupants' in residentView.body));
  await screen(resident,'resident.png');
  phase='NARROW_SCREEN';activePage=responder;pageRole='responder';
  await responder.request('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await delay(500);
  check('mobile_document_has_no_horizontal_overflow',await responder.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1'));
  await screen(responder,'mobile.png');
  await responder.request('Emulation.clearDeviceMetricsOverride');
  phase='SOURCE_EXPIRY';console.log(JSON.stringify({test:summary.test,phase:'WAIT_SOURCE_EXPIRY_31_SECONDS'}));
  await delay(31000);
  await until(()=>responder.evaluate('document.querySelector("#guidance").textContent==="관측 만료"'));
  await responder.evaluate('document.querySelector("#mode").value="fixed";document.querySelector("#mode").dispatchEvent(new Event("change"));true');
  check('expired_guidance_clears_exit_and_path',await responder.evaluate('document.querySelector("#exit").textContent==="—"&&document.querySelectorAll("#path li").length===0&&document.querySelectorAll("#map .edge.active").length===0'));
  check('historical_people_label_and_selection_retained',await responder.evaluate(`document.querySelector('#snapshot-note').textContent.includes('저장 기록 보기')&&!document.querySelector('#person').disabled&&document.querySelector('#person').value===${JSON.stringify(selected)}`));
  await screen(responder,'expired-history.png');
  if(finishRecording){summary.video=await finishRecording();finishRecording=null;}
  phase='LOGOUT_AND_RELOAD';await click(responder,'#logout');
  await until(()=>responder.evaluate('!document.querySelector("#login").hidden'));
  check('logout_clears_people_and_session',(await api(responder,'/api/v1/session')).status===401&&await responder.evaluate('document.querySelector("#person").disabled'));
  check('no_unhandled_page_exceptions',browser.protocol.events.length===0);
  summary.state='PASS';summary.phase='COMPLETE';
} catch(error) {
  summary.state=started||error?.code==='DOCUMENT_NOT_READY'?'FAIL':'BLOCKED';summary.phase=phase;
  // Error messages are fixed driver/check names, never raw CDP params or codes.
  const failure=safeFailure(error);summary.reason=failure.code;
  const diagnostics={phase,failure,pageRole,lastControl};
  if(activePage){
    try{diagnostics.rendered=await renderedState(activePage);}catch{diagnostics.rendered='UNAVAILABLE';}
    // A screenshot is allowed only after the hidden login form's password was cleared.
    try{if(await activePage.evaluate('document.querySelector("#login")?.hidden===true && document.querySelector("#code")?.value===""')){
      const shot=await activePage.request('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await writeFile(join(directory,'failure.png'),Buffer.from(shot.data,'base64'));
    }}catch{diagnostics.screenshot='UNAVAILABLE';}
  }
  await save('failure.json',diagnostics);
} finally {
  if(finishRecording){try{summary.video=await finishRecording();}catch{summary.video='CAPTURE_INCOMPLETE';}}
  if(browser)await browser.close();
  summary.checks=Object.keys(checks).length;summary.failed_checks=Object.keys(checks).filter(k=>!checks[k]);
  await save('assertions.json',checks);
  await save('summary.json',summary);
  await save('meta.json',{origin,input:'SYNTHETIC',MEC:'unavailable',Hosted:'NOT_CONTACTED',
    capture:'REAL_CHROME_RENDERING_NOT_HTTP_ONLY',credentials:'NEVER_EXPORTED',
    source_sha256:createHash('sha256').update(await readFile(new URL(import.meta.url))).digest('hex'),
    driver_sources:Object.fromEntries(await Promise.all(['dashboard.mjs','cdp.mjs','controls.mjs','record.mjs','fonts.mjs'].map(async name=>
      [name,createHash('sha256').update(await readFile(new URL(name,import.meta.url))).digest('hex')])))});
  console.log(JSON.stringify({...summary,evidence:directory}));
}
process.exitCode=summary.state==='PASS'?0:1;
