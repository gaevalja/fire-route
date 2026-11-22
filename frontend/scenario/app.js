import {routeFor,timeLabel,selectedResident,freshPeople,rememberPeople,peoplePresentation,residentOptionsKey,mecLabel,zoneRouteFor,zoneSummary,roomOptions,estimatePresentation} from '/model.mjs';
import {BuildingView,describeZone,RESIDENT_STATES} from '/building-view.mjs';
import {FrameRecorder,TimelinePlayer,TimelinePanel} from '/timeline.mjs';
import './locale.js';
const $=id=>document.getElementById(id);
const locale=globalThis.FireRouteLocale;
const {t,getLanguage}=locale;
locale.localize(document);
let role=null,building=null,view=null,busy=false,incident=null,savedPeople=null,peopleKey=null;
// Evacuation timeline: live responder frames recorded in this tab only (see timeline.mjs).
const recorder=new FrameRecorder(),player=new TimelinePlayer();
let timeline=null;
let nodeFloor=new Map(),edgeLength=new Map();
// The chosen room is a per-browser convenience only; it is never sent to the CSE.
function readZone(){try{return localStorage.getItem('fr-my-zone')||'';}catch{return '';}}
function storeZone(value){try{value?localStorage.setItem('fr-my-zone',value):localStorage.removeItem('fr-my-zone');}catch{}}
let myZone=readZone();
let movement={kind:'UNAVAILABLE',data:null};
const labels={ROUTE_AVAILABLE:['계산 경로 있음','Route available'],NO_VERIFIED_ROUTE:['확인된 경로 없음','No verified route'],
  PENDING:['대조 중','Verifying'],STALE:['관측 만료','Observation expired'],UNKNOWN:['확인 불가','Unknown']};
const floorLabel=floor=>floor===11?t('11층 옥상','Roof (floor 11)'):t(`${floor}층`,`Floor ${floor}`);
function text(tag,value){const el=document.createElement(tag);el.textContent=value;return el;}
function svg(tag,attrs){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);return el;}
async function api(path,options={}){
  let response;
  try{response=await fetch(path,{cache:'no-store',...options,headers:{'Content-Type':'application/json'}});}
  catch{throw new Error(t('시연 서버에 연결할 수 없습니다.','Cannot connect to the demo server.'));}
  const body=await response.json();if(response.status===401){login();throw new Error(t('접속 코드를 확인하세요.','Check your access code.'));}
  if(!response.ok){const error=new Error(response.status===409?t('이전 작업을 처리하고 있습니다.','The previous action is still running.'):t('현재 정보를 확인할 수 없습니다.','Current information is unavailable.'));error.body=body;throw error;}return body;
}
function resetTimeline(){recorder.clear();player.goLive();timeline?.refresh();}
function changeIncident(value){if(value!==incident){incident=value;savedPeople=null;peopleKey=null;$('person').value='';resetTimeline();}}
function showModelReplay(show){
  const frame=$('model-replay');
  $('live-simulator').hidden=show;
  frame.hidden=!show;
  $('show-live').setAttribute('aria-pressed',String(!show));
  $('show-model-replay').setAttribute('aria-pressed',String(show));
  if(show&&!frame.hasAttribute('src'))frame.src='/model-replay/replay.html';
  if(!show&&frame.hasAttribute('src'))frame.contentWindow.postMessage('pause-model-replay',location.origin);
}
function login(){role=null;view=null;incident=null;savedPeople=null;peopleKey=null;pickedNode=null;runtimeState=null;showModelReplay(false);$('model-replay').removeAttribute('src');$('simulator-views').hidden=true;resetTimeline();renderSceneInfo();renderRuntime();render(null);$('app').hidden=true;$('login').hidden=false;}
function fillZones(){
  const select=$('my-zone'),items=[select.options[0]];
  for(const group of roomOptions(building)){const optgroup=document.createElement('optgroup');optgroup.label=floorLabel(group.floor);for(const id of group.rooms){const option=text('option',id);option.value=id;optgroup.append(option);}items.push(optgroup);}
  select.replaceChildren(...items);
  if(!building.nodes.some(n=>n.id===myZone&&n.kind==='room')){myZone='';storeZone('');}
  select.value=myZone;
}
async function signed(value){role=value;incident=null;savedPeople=null;peopleKey=null;building=await api('/api/v1/building');
  nodeFloor=new Map(building.nodes.map(n=>[n.id,n.floor]));
  edgeLength=new Map(building.edges.flatMap(e=>[[e.from+'|'+e.to,e.length_m],[e.to+'|'+e.from,e.length_m]]));
  scene?.setBuilding(building);recorder.setBuilding(building);player.goLive();timeline?.refresh();
  fillZones();render(null);$('login').hidden=true;$('app').hidden=false;for(const id of ['controls','private','tl-body'])$(id).hidden=role!=='responder';
  $('simulator-views').hidden=role!=='responder';
  // The timeline stays visible for residents, but only explains why playback needs a responder login.
  $('tl-resident-note').hidden=role==='responder';$('moving-option').hidden=role!=='responder';$('mode').value='fixed';$('mode').dispatchEvent(new Event('change'));await poll();}
function coords(node){
  if(node.kind==='roof')return [420,210];
  if(node.kind==='exit')return [node.id==='EXIT_A'?300:540,385];
  const match=node.id.match(/-(R|C)(\d+)$/);
  if(match){const n=Number(match[2]);if(match[1]==='C')return [180+(n-1)*120,210];const column=n<=5?n:{6:1,7:2,8:4,9:5}[n];return [180+(column-1)*120,n<=5?80:320];}
  if(node.kind==='lobby')return [420,210];if(node.kind==='elevator')return [420,320];return [node.id.endsWith('SA')?60:780,210];
}
// ---------------------------------------------------------------------------------------------
// Map. One shared state per frame drives both views:
//   - the WebGL building view (3D / 2D plan), when the browser supports WebGL;
//   - the original SVG node schematic, always kept up to date as the fallback.
// ---------------------------------------------------------------------------------------------

let scene=null, pickedNode=null, webglUnavailable=false;
const RENDER_MODES=['3d','2d','schematic'];
const RENDER_MODE_KEY='fr-render-mode'; // per-browser convenience only
function readRenderMode(){try{const value=localStorage.getItem(RENDER_MODE_KEY);return RENDER_MODES.includes(value)?value:'3d';}catch{return '3d';}}
function storeRenderMode(value){try{localStorage.setItem(RENDER_MODE_KEY,value);}catch{}}

/** Fraction of the current link that a moving resident has walked (0–1). */
function progressRatio(person){
  if(!person?.target)return 0;
  const length=edgeLength.get(person.node+'|'+person.target);
  return length?Math.min(1,person.progress_m/length):0;
}

/** The route the map draws for a live view: the chosen room's route, else the fixed-origin route. */
function livePath(data){
  const zonePath=zoneRouteFor(data,myZone);
  return zonePath.length?zonePath:routeFor(data);
}

/** Everything the map shows: the live frame, or a recorded frame while the timeline is replaying. */
function mapState(){
  const moving=$('mode').value==='moving';
  const floor=Number($('floor').value);
  // The 3D/2D view marks the room the guidance starts from: the chosen room, else the fixed origin.
  const origin=moving?null:(myZone||view?.fixed_origin||null);
  const showCrowd=role==='responder'&&$('show-crowd').checked;

  const frame=timeline?.replaying?recorder.sample(player.position(recorder)):null;
  if(frame){
    const chosen=$('person').value;
    const person=moving?(frame.residents.find(p=>p.id===chosen)||frame.residents[0]||null):null;
    return {
      floor,moving,origin,replay:true,
      path:moving?(person?.target?[person.node,person.target]:[]):frame.path,
      blocked:frame.blocked,
      hazards:frame.hazards,
      person:person?{id:person.id,node:person.node,target:person.target,ratio:person.ratio,historical:false}:null,
      crowd:showCrowd?frame.residents:[],
    };
  }

  const data=moving?movement.data:view;
  const person=selectedResident(movement.data,$('person').value);
  const residents=movement.data?.residents||[];
  return {
    floor,moving,origin,replay:false,
    path:moving?(person?.target?[person.node,person.target]:[]):livePath(view),
    blocked:new Set(data?.hazards?.blocked_nodes||[]),
    hazards:new Map((data?.hazards?.zones||[]).map(zone=>[zone.zone_id,zone])),
    person:moving&&person?{id:person.resident_id,node:person.node,target:person.target,ratio:progressRatio(person),historical:movement.kind==='HISTORICAL'}:null,
    crowd:showCrowd?residents.map(p=>({id:p.resident_id,node:p.node,target:p.target,ratio:progressRatio(p),status:p.status})):[],
  };
}

/** Floor of a resident as drawn: the next zone once they are past the middle of a link. */
function residentFloor(person){
  return nodeFloor.get(person.target&&person.ratio>0.5?person.target:person.node);
}

/** Floor shortcut buttons (like fire_evac/replay.js): people still inside and fire per floor. */
function setupFloorTabs(){
  const tabs=$('floor-tabs');
  for(let floor=1;floor<=11;floor+=1){
    const button=text('button','');button.type='button';button.dataset.floor=String(floor);
    button.append(text('span',''),Object.assign(text('small',''),{className:'count'}));
    button.addEventListener('click',()=>{$('floor').value=String(floor);$('tl-follow').checked=false;draw();});
    tabs.append(button);
  }
}
function renderFloorTabs(state){
  const people=new Map(),fire=new Set();
  for(const person of state.crowd)if(person.status!=='EVACUATED'){const floor=residentFloor(person);people.set(floor,(people.get(floor)||0)+1);}
  for(const [id,zone] of state.hazards)if(zone.fire_index>0)fire.add(nodeFloor.get(id));
  for(const button of $('floor-tabs').children){
    const floor=Number(button.dataset.floor),count=people.get(floor);
    button.classList.toggle('active',floor===state.floor);
    button.classList.toggle('fire',fire.has(floor));
    button.setAttribute('aria-pressed',String(floor===state.floor));
    button.querySelector('span').textContent=floor===11?t('옥상','Roof'):floor+'F';
    button.querySelector('.count').textContent=count?t(`${count}명`,String(count)):'';
    button.title=floorLabel(floor)+(count?t(` · ${count}명`,` · ${count} remaining`):'')+(fire.has(floor)?t(' · 화재',' · Fire'):'');
  }
}

/** SVG node schematic of the selected floor. */
function drawSchematic(state){
  const root=$('map');
  const meta=new Map(building.nodes.map(n=>[n.id,n]));
  const onRoute=new Set(state.path);
  const routeUses=(a,b)=>state.path.some((n,i)=>i>0&&((state.path[i-1]===a&&n===b)||(state.path[i-1]===b&&n===a)));

  for(const edge of building.edges){
    const a=meta.get(edge.from),b=meta.get(edge.to);
    if(a.floor!==state.floor||b.floor!==state.floor)continue;
    const [x1,y1]=coords(a),[x2,y2]=coords(b);
    root.append(svg('line',{x1,y1,x2,y2,class:routeUses(a.id,b.id)?'edge active':'edge'}));
  }

  for(const node of building.nodes){
    if(node.floor!==state.floor)continue;
    const [x,y]=coords(node);
    let look='';
    if(state.blocked.has(node.id))look=' blocked';
    else if(onRoute.has(node.id))look=' selected';
    else if(state.hazards.get(node.id)?.fire_index>0)look=' hazard';
    if(!state.moving&&node.id===myZone)look+=' origin';
    const group=svg('g',{class:'node'+look});
    group.append(svg('circle',{cx:x,cy:y,r:node.kind==='exit'?22:17}));
    const label=svg('text',{x,y:y+36,'text-anchor':'middle'});
    label.textContent=node.id;
    group.append(label);
    root.append(group);
  }

  const person=state.person;
  const at=person&&meta.get(person.node);
  if(!at||at.floor!==state.floor)return;
  let [x,y]=coords(at);
  const target=person.target&&meta.get(person.target);
  if(target?.floor===state.floor){
    const [tx,ty]=coords(target);
    x+=(tx-x)*person.ratio;
    y+=(ty-y)*person.ratio;
  }
  const dot=svg('circle',{cx:x,cy:y,r:9,class:'person'+(person.historical?' historical':'')});
  const title=svg('title',{});
  title.textContent=person.historical?t('저장 당시 위치','Recorded position'):t('현재 모의 프레임의 위치','Position in the current simulation frame');
  dot.append(title);
  root.append(dot);
}

function draw(){
  $('map').replaceChildren();
  if(!building)return;
  let state=mapState();
  if($('tl-follow').checked&&state.person){
    const floor=residentFloor(state.person);
    if(floor&&floor!==state.floor){$('floor').value=String(floor);state={...state,floor};}
  }
  renderFloorTabs(state);
  drawSchematic(state);
  scene?.update(state,state.floor);
}

function applyRenderMode(){
  const mode=scene?$('render-mode').value:'schematic';
  const webgl=mode!=='schematic';
  $('scene').hidden=!webgl;
  $('scene-help').hidden=!webgl;
  $('view-reset').hidden=!webgl;
  $('scene-info').hidden=!webgl&&!$('scene-info').textContent;
  $('map').toggleAttribute('hidden',webgl); // SVG elements have no .hidden property
  $('legend').textContent=webgl
    ?t('초록: 계산 경로 · 주황: 화재 · 회색: 연기 · 빨강: 차단 · 진한 빨강: 붕괴 · 파랑: 기준 위치와 선택한 가상 주민',
      'Green — route · orange — fire · gray — smoke · red — blocked · dark red — collapse · blue — origin and selected resident')
    :t('초록: 계산 경로 · 주황: 모의 위험 · 빨강: 차단 · 파랑 점: 선택한 가상 주민','Green — route · orange — hazard · red — blocked · blue dot — selected resident');
  if(webgl)scene.setMode(mode);
  draw();
}

/** Called when WebGL cannot start or the GPU context is lost: fall back to the SVG schematic. */
function sceneUnavailable(){
  scene=null;
  webglUnavailable=true;
  for(const value of ['3d','2d'])$('render-mode').querySelector(`option[value="${value}"]`).disabled=true;
  $('render-mode').value='schematic';
  renderSceneInfo();
  applyRenderMode();
}

/** A click on the 3D/2D view: describe the zone and jump to its floor. */
function showPick(pick){
  pickedNode=pick?.node||null;
  renderSceneInfo();
  if(pick&&pick.node.kind!=='exit'&&String(pick.node.floor)!==$('floor').value){
    $('floor').value=String(pick.node.floor);
    draw();
  }
}

function renderSceneInfo(){
  $('scene-info').textContent=pickedNode ? describeZone(pickedNode,mapState()) : webglUnavailable
    ?t('이 브라우저에서 WebGL을 사용할 수 없어 노드 모식도로 표시합니다.','WebGL is unavailable. Showing the node diagram.') : '';
}

function setupScene(){
  $('render-mode').value=readRenderMode();
  try{scene=new BuildingView($('scene-canvas'),$('scene-labels'),{onPick:showPick,onLost:sceneUnavailable});}
  catch{sceneUnavailable();return;}
  applyRenderMode();
}
function personDescription(){
  const person=selectedResident(movement.data,$('person').value);
  if(!person)return movement.data?t('이 실행에는 가상 주민이 없습니다.','This run has no simulated residents.')
    :t('주민 기록을 읽지 못했습니다. 연결 또는 초기화 상태를 확인하세요.','Resident records are unavailable. Check the connection or reset the scenario.');
  const prefix=movement.kind==='HISTORICAL'?t('저장 당시 상태 · ','Recorded state · '):'';
  const state=RESIDENT_STATES[person.status];
  const status=state?t(state.label,state.english):person.status;
  return `${prefix}${status} · ${person.node}`+(person.target?` → ${person.target} · ${t('통로','Link')} ${person.progress_m.toFixed(1)} m`:'');
}

function renderDetailTitle(){
  $('detail-title').textContent=$('mode').value==='moving'&&role==='responder'
    ?t('가상 주민 이동','Simulated resident movement')
    :myZone?t('내 위치의 최신 안내','Latest guidance from your room'):t('고정 위치의 최신 안내','Latest guidance from the fixed origin');
}
function render(next){
  $('mec-badge').textContent=t('10층 + 옥상 · 합성 162구역 · ','10 floors + roof · 162 simulated zones · ')+mecLabel(next);
  view=next;const status=next?.guidance_status||'UNKNOWN',path=routeFor(next);$('clock').textContent=timeLabel(next?.simulation_second);$('guidance').textContent=t(...(labels[status]||labels.UNKNOWN));$('exit').textContent=path.length?next.route.target_exit:'—';$('acks').textContent=(next?.delivery?.ack_count??'—')+' / 3';
  movement=role==='responder'?peoplePresentation(next,savedPeople,incident):{kind:'UNAVAILABLE',data:null};
  const people=movement.data;
  $('notice').textContent=status==='ROUTE_AVAILABLE'?t('현재 CSE의 고정 출발점 안내입니다. 가정된 모델의 계산 결과입니다.','The CSE provides fixed-origin guidance calculated from the assumed model.')
    :status==='STALE'?t('실시간 관측이 만료되어 방향 안내를 숨깁니다. 아래 저장 기록은 현재 위치 정보가 아닙니다.','Live observations expired. Saved positions are shown at their recorded time.')
    :status==='PENDING'?t('현재 프레임·경로·장치 ACK를 대조하고 있습니다.','Checking the current frame, route and device ACKs.')
    :t('현재 방향 안내를 확인할 수 없습니다.','Current route guidance is unavailable.');
  $('snapshot-note').hidden=role!=='responder';
  const stamp=people?.snapshot_at_utc||people?.observed_at_utc;
  const historical=movement.kind==='HISTORICAL';
  $('snapshot-note').textContent=people?(historical?t('저장 기록 보기','Saved snapshot'):t('현재 프레임','Current frame'))
    +t(' · 모의 ',' · Simulation ')+timeLabel(people.simulation_second)
    +(stamp?t(' · 저장 ',' · Recorded ')+new Date(stamp).toLocaleString(getLanguage()):'')
    +(historical?t(' · 인원 수와 파란 점은 저장 당시 기록입니다.',' · Counts and blue markers reflect the recorded time.'):'')
    :t('주민 기록을 확인하고 있습니다. 시나리오 초기화 또는 CSE 연결 상태를 확인하세요.','Checking resident records. Check the CSE connection or reset the scenario.');
  const zonePath=zoneRouteFor(next,myZone),zone=zoneSummary(next,myZone);
  const noDirection=t('방향 없음','No directions');
  const origin=t('고정 출발점 ','Fixed origin ')+(next?.fixed_origin||'F7-R3');
  const exit=path.length?next.route.target_exit:noDirection;
  if(myZone)$('fixed-detail').replaceChildren(text('p',t('내 위치 ','Your room ')+myZone),text('strong',zonePath.length?next.zone_route.target_exit:noDirection),text('p',origin+' · '+exit));
  else $('fixed-detail').replaceChildren(text('p',origin),text('strong',exit));
  $('zone-state').textContent=zone?zone.text:'';
  renderDetailTitle();
  $('path').replaceChildren(...(myZone?zonePath:path).map(n=>text('li',n)));
  const estimate=estimatePresentation(next);$('estimate-summary').textContent=estimate.summary;
  if(estimate.rows.length){const grid=text('table',''),top=text('tr','');for(const label of t(['순위','구역','추정 인원','재실 확률','근거','마지막 감지','위험'],['Rank','Zone','Est. occupants','Occupancy likelihood','Evidence','Last detection','Hazard']))top.append(text('th',label));grid.append(top);
    for(const row of estimate.rows){const tr=text('tr','');const chance=text('td',row.likelihood+' '+row.probability);chance.className='likely-'+row.level;tr.append(text('td',row.rank),text('td',row.zone),text('td',row.count),chance,text('td',row.basis),text('td',row.last),text('td',row.hazard));grid.append(tr);}
    $('estimate-table').replaceChildren(grid);}
  else $('estimate-table').replaceChildren(text('p',estimate.state==='ESTIMATED'?t('재실 가능성이 있는 구역이 추정되지 않았습니다.','The estimate found no likely occupied zones.'):t('표시할 추정이 없습니다.','No occupancy estimates available.')));
  for(const [id,key] of [['total','total'],['evacuated','evacuated'],['remaining','remaining']])$(id).textContent=people?.population?people.population[key]:'UNKNOWN';$('queued').textContent=people?.population?(people.population.states.QUEUED||0):'UNKNOWN';
  const key=people?residentOptionsKey(people):null;
  if(key!==peopleKey||peopleKey===null){
    const previous=$('person').value,items=(people?.residents||[]).map(p=>{const option=text('option',p.resident_id);option.value=p.resident_id;return option;});
    if(!items.length){const option=text('option',people?t('이 실행에는 가상 주민이 없습니다','This run has no simulated residents'):t('저장된 주민 기록을 확인 중입니다','Checking saved resident records'));option.value='';items.push(option);}
    $('person').replaceChildren(...items);if(people?.residents.some(p=>p.resident_id===previous))$('person').value=previous;peopleKey=key;
  }
  $('person').disabled=!people?.residents?.length;$('person-state').textContent=personDescription();
  const table=text('table',''),head=text('tr','');for(const label of t(['마지막 도착 구역','잔류 인원','그중 이동 중'],['Last reached zone','Remaining occupants','In transit']))head.append(text('th',label));table.append(head);for(const row of people?.occupants||[]){const tr=text('tr','');tr.append(text('td',row.zone_id),text('td',row.remaining_count),text('td',row.moving_count));table.append(tr);}$('occupants').replaceChildren(people?.occupants?table:text('p',t('인원 기록을 확인할 수 없습니다','Occupant records are unavailable')));draw();
}
let scenarioRunning=false; // polls faster while the scenario plays so the timeline records more frames
let runtimeState=null;
function renderRuntime(){
  const state=runtimeState;
  $('runtime').textContent=state?state.state+(state.paused?t(' · 일시정지',' · Paused'):t(' · 자동 진행',' · Running'))
    :t('처리 상태 확인 중','Checking simulator status');
}
async function poll(){
  if(!role||busy)return;busy=true;
  try{const state=await api('/api/v1/status');changeIncident(state.incident_id);scenarioRunning=!state.paused;runtimeState=state;renderRuntime();for(const b of document.querySelectorAll('[data-action]'))b.disabled=state.busy;if(!incident){render(null);return;}
    const current=await api(`/api/v1/incidents/${incident}/${role==='responder'?'responder':'resident'}${myZone?'/'+encodeURIComponent(myZone):''}`);
    if(role==='responder'){
      savedPeople=rememberPeople(savedPeople,current,incident);
      if(!freshPeople(current,incident)&&(!savedPeople||Number.isInteger(current.route_version)&&current.route_version>savedPeople.route_version)){
        try{const record=await api(`/api/v1/incidents/${incident}/snapshot`);savedPeople=rememberPeople(savedPeople,record,incident);}catch(error){if(!role)throw error;}
      }
    }
    // Record before drawing so a live timeline already includes this frame.
    if(role==='responder'&&freshPeople(current,incident)&&recorder.record(current,livePath(current)))timeline?.refresh();
    render(current);
  }
  catch(error){render(error.body?.guidance_status?error.body:null);}finally{busy=false;}
}
async function pollLoop(){
  try{await poll();}finally{setTimeout(pollLoop,scenarioRunning?800:1500);}
}
for(let floor=1;floor<=11;floor++){const option=text('option',floorLabel(floor));option.value=String(floor);$('floor').append(option);}$('floor').value='7';$('floor').addEventListener('change',draw);
$('mode').addEventListener('change',()=>{const moving=$('mode').value==='moving'&&role==='responder';$('fixed-detail').hidden=moving;$('moving-detail').hidden=!moving;$('path').hidden=moving;$('zone-picker').hidden=moving;renderDetailTitle();if(moving)$('person').dispatchEvent(new Event('change'));draw();});
$('my-zone').addEventListener('change',()=>{myZone=$('my-zone').value;storeZone(myZone);const n=building?.nodes.find(n=>n.id===myZone);if(n)$('floor').value=String(n.floor);render(null);poll();});
$('person').addEventListener('change',()=>{const p=selectedResident(movement.data,$('person').value);$('person-state').textContent=personDescription();if(p){const n=building.nodes.find(n=>n.id===p.node);if(n)$('floor').value=String(n.floor);}draw();});
$('login-form').addEventListener('submit',async event=>{event.preventDefault();try{const result=await api('/api/v1/session',{method:'POST',body:JSON.stringify({role:$('role').value,access_code:$('code').value})});$('code').value='';$('error').textContent='';await signed(result.role);}catch(error){$('error').textContent=error.message;}});
$('logout').addEventListener('click',async()=>{try{await api('/api/v1/session',{method:'DELETE'});}finally{login();}});
$('show-live').addEventListener('click',()=>{showModelReplay(false);draw();});
$('show-model-replay').addEventListener('click',()=>{if(role==='responder')showModelReplay(true);});
for(const button of document.querySelectorAll('[data-action]'))button.addEventListener('click',async()=>{try{await api('/api/v1/scenario',{method:'POST',body:JSON.stringify({action:button.dataset.action})});render(null);await poll();}catch(error){$('notice').textContent=error.message;}});
$('render-mode').addEventListener('change',()=>{storeRenderMode($('render-mode').value);pickedNode=null;renderSceneInfo();applyRenderMode();});
$('view-reset').addEventListener('click',()=>scene?.resetCamera());
$('show-crowd').addEventListener('change',draw);
$('tl-follow').addEventListener('change',draw);
setupFloorTabs();
timeline=new TimelinePanel(recorder,player,{onChange:draw});
timeline.onFloor=floor=>{$('floor').value=String(floor);$('tl-follow').checked=false;};
setupScene();
function sendLanguage(){
  const frame=$('model-replay');
  if(frame.hasAttribute('src'))frame.contentWindow.postMessage({type:'fireroute-language',language:getLanguage()},location.origin);
}
$('model-replay').addEventListener('load',sendLanguage);
$('language-select').value=getLanguage();
$('language-select').addEventListener('change',event=>locale.setLanguage(event.target.value));
locale.onChange(()=>{
  locale.localize(document);
  $('language-select').value=getLanguage();
  $('error').textContent='';
  for(const option of $('floor').options)option.textContent=floorLabel(Number(option.value));
  if(building)fillZones();
  if(!$('person').value)peopleKey=null;
  renderRuntime();
  timeline.refresh();
  render(view);
  renderSceneInfo();
  applyRenderMode();
  sendLanguage();
});
setTimeout(pollLoop,1500);api('/api/v1/session').then(result=>signed(result.role)).catch(()=>login());
