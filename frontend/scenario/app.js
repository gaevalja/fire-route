import {routeFor,timeLabel,selectedResident,freshPeople,rememberPeople,peoplePresentation,residentOptionsKey} from '/model.mjs';
const $=id=>document.getElementById(id);
let role=null,building=null,view=null,busy=false,incident=null,savedPeople=null,peopleKey=null;
let movement={kind:'UNAVAILABLE',data:null};
const labels={ROUTE_AVAILABLE:'계산 경로 있음',NO_VERIFIED_ROUTE:'확인된 경로 없음',PENDING:'대조 중',STALE:'관측 만료',UNKNOWN:'확인 불가'};
function text(tag,value){const el=document.createElement(tag);el.textContent=value;return el;}
function svg(tag,attrs){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);return el;}
async function api(path,options={}){
  const response=await fetch(path,{cache:'no-store',...options,headers:{'Content-Type':'application/json'}});
  const body=await response.json();if(response.status===401){login();throw new Error('접속 코드를 확인하세요.');}
  if(!response.ok){const error=new Error(response.status===409?'이전 작업을 처리하고 있습니다.':'현재 정보를 확인할 수 없습니다.');error.body=body;throw error;}return body;
}
function changeIncident(value){if(value!==incident){incident=value;savedPeople=null;peopleKey=null;$('person').value='';}}
function login(){role=null;view=null;incident=null;savedPeople=null;peopleKey=null;render(null);$('app').hidden=true;$('login').hidden=false;}
async function signed(value){role=value;incident=null;savedPeople=null;peopleKey=null;building=await api('/api/v1/building');render(null);$('login').hidden=true;$('app').hidden=false;for(const id of ['controls','private'])$(id).hidden=role!=='responder';$('moving-option').hidden=role!=='responder';$('mode').value='fixed';$('mode').dispatchEvent(new Event('change'));await poll();}
function coords(node){
  if(node.kind==='roof')return [420,210];
  if(node.kind==='exit')return [node.id==='EXIT_A'?300:540,385];
  const match=node.id.match(/-(R|C)(\d+)$/);
  if(match){const n=Number(match[2]);if(match[1]==='C')return [180+(n-1)*120,210];const column=n<=5?n:{6:1,7:2,8:4,9:5}[n];return [180+(column-1)*120,n<=5?80:320];}
  if(node.kind==='lobby')return [420,210];if(node.kind==='elevator')return [420,320];return [node.id.endsWith('SA')?60:780,210];
}
function draw(){
  const root=$('map');root.replaceChildren();if(!building)return;
  const floor=Number($('floor').value),nodes=building.nodes.filter(n=>n.floor===floor),meta=new Map(building.nodes.map(n=>[n.id,n]));
  const moving=$('mode').value==='moving',mapData=moving?movement.data:view;
  const person=selectedResident(movement.data,$('person').value);
  const path=moving?(person?.target?[person.node,person.target]:[]):routeFor(view),selected=new Set(path),blocks=new Set(mapData?.hazards?.blocked_nodes||[]),levels=new Map((mapData?.hazards?.zones||[]).map(z=>[z.zone_id,z]));
  for(const edge of building.edges){const a=meta.get(edge.from),b=meta.get(edge.to);if(a.floor!==floor||b.floor!==floor)continue;const [x1,y1]=coords(a),[x2,y2]=coords(b);const active=path.some((n,i)=>i&&((path[i-1]===a.id&&n===b.id)||(path[i-1]===b.id&&n===a.id)));root.append(svg('line',{x1,y1,x2,y2,class:active?'edge active':'edge'}));}
  for(const n of nodes){const [x,y]=coords(n),hazard=levels.get(n.id);const group=svg('g',{class:'node'+(blocks.has(n.id)?' blocked':selected.has(n.id)?' selected':hazard?.fire_index>0?' hazard':'')});group.append(svg('circle',{cx:x,cy:y,r:n.kind==='exit'?22:17}));const label=svg('text',{x,y:y+36,'text-anchor':'middle'});label.textContent=n.id;group.append(label);root.append(group);}
  if(moving){const p=person;const n=p&&meta.get(p.node);if(n?.floor===floor){let [x,y]=coords(n);const target=p.target&&meta.get(p.target);if(target?.floor===floor){const edge=building.edges.find(e=>(e.from===p.node&&e.to===p.target)||(e.to===p.node&&e.from===p.target));const [tx,ty]=coords(target);const ratio=edge?Math.min(1,p.progress_m/edge.length_m):0;x+=(tx-x)*ratio;y+=(ty-y)*ratio;}const dot=svg('circle',{cx:x,cy:y,r:9,class:'person'+(movement.kind==='HISTORICAL'?' historical':'')});const title=svg('title',{});title.textContent=movement.kind==='HISTORICAL'?'저장 당시 위치':'현재 모의 프레임의 위치';dot.append(title);root.append(dot);}}
}
function personDescription(){
  const person=selectedResident(movement.data,$('person').value);
  const prefix=movement.kind==='HISTORICAL'?'저장 당시 상태 · ':'';
  return person?`${prefix}${person.status} · ${person.node}${person.target?' → '+person.target+' · 통로 '+person.progress_m.toFixed(1)+' m':''}`:movement.data?'이 실행에는 가상 주민이 없습니다.':'주민 기록을 읽지 못했습니다. 연결 또는 초기화 상태를 확인하세요.';
}
function render(next){
  view=next;const status=next?.guidance_status||'UNKNOWN',path=routeFor(next);$('clock').textContent=timeLabel(next?.simulation_second);$('guidance').textContent=labels[status]||labels.UNKNOWN;$('exit').textContent=path.length?next.route.target_exit:'—';$('acks').textContent=(next?.delivery?.ack_count??'—')+' / 3';
  movement=role==='responder'?peoplePresentation(next,savedPeople,incident):{kind:'UNAVAILABLE',data:null};
  const people=movement.data;
  $('notice').textContent=status==='ROUTE_AVAILABLE'?'현재 CSE의 고정 출발점 안내입니다. 가정된 모델의 계산 결과입니다.':status==='STALE'?'실시간 관측이 만료되어 방향 안내를 숨깁니다. 아래 저장 기록은 현재 위치 정보가 아닙니다.':status==='PENDING'?'현재 프레임·경로·장치 ACK를 대조하고 있습니다.':'현재 방향 안내를 확인할 수 없습니다.';
  $('snapshot-note').hidden=role!=='responder';
  const stamp=people?.snapshot_at_utc||people?.observed_at_utc;
  $('snapshot-note').textContent=people?(movement.kind==='HISTORICAL'?'저장 기록 보기':'현재 프레임')+' · 모의 '+timeLabel(people.simulation_second)+(stamp?' · 저장 '+new Date(stamp).toLocaleString('ko-KR'):'')+(movement.kind==='HISTORICAL'?' · 인원 수와 파란 점은 저장 당시 기록입니다.':''):'주민 기록을 확인하고 있습니다. 시나리오 초기화 또는 CSE 연결 상태를 확인하세요.';
  $('fixed-detail').replaceChildren(text('p','고정 출발점 '+(next?.fixed_origin||'F7-R3')),text('strong',path.length?next.route.target_exit:'방향 없음'));
  $('path').replaceChildren(...path.map(n=>text('li',n)));
  for(const [id,key] of [['total','total'],['evacuated','evacuated'],['remaining','remaining']])$(id).textContent=people?.population?people.population[key]:'UNKNOWN';$('queued').textContent=people?.population?(people.population.states.QUEUED||0):'UNKNOWN';
  const key=people?residentOptionsKey(people):null;
  if(key!==peopleKey||peopleKey===null){
    const previous=$('person').value,items=(people?.residents||[]).map(p=>{const option=text('option',p.resident_id);option.value=p.resident_id;return option;});
    if(!items.length){const option=text('option',people?'이 실행에는 가상 주민이 없습니다':'저장된 주민 기록을 확인 중입니다');option.value='';items.push(option);}
    $('person').replaceChildren(...items);if(people?.residents.some(p=>p.resident_id===previous))$('person').value=previous;peopleKey=key;
  }
  $('person').disabled=!people?.residents?.length;$('person-state').textContent=personDescription();
  const table=text('table',''),head=text('tr','');for(const label of ['마지막 도착 구역','잔류 인원','그중 이동 중'])head.append(text('th',label));table.append(head);for(const row of people?.occupants||[]){const tr=text('tr','');tr.append(text('td',row.zone_id),text('td',row.remaining_count),text('td',row.moving_count));table.append(tr);}$('occupants').replaceChildren(people?.occupants?table:text('p','인원 기록을 확인할 수 없습니다'));draw();
}
async function poll(){
  if(!role||busy)return;busy=true;
  try{const state=await api('/api/v1/status');changeIncident(state.incident_id);$('runtime').textContent=state.state+(state.paused?' · 일시정지':' · 자동 진행');for(const b of document.querySelectorAll('[data-action]'))b.disabled=state.busy;if(!incident){render(null);return;}
    const current=await api(`/api/v1/incidents/${incident}/${role==='responder'?'responder':'resident'}`);
    if(role==='responder'){
      savedPeople=rememberPeople(savedPeople,current,incident);
      if(!freshPeople(current,incident)&&(!savedPeople||Number.isInteger(current.route_version)&&current.route_version>savedPeople.route_version)){
        try{const record=await api(`/api/v1/incidents/${incident}/snapshot`);savedPeople=rememberPeople(savedPeople,record,incident);}catch(error){if(!role)throw error;}
      }
    }
    render(current);
  }
  catch(error){render(error.body?.guidance_status?error.body:null);}finally{busy=false;}
}
for(let floor=1;floor<=11;floor++){const option=text('option',floor===11?'11층 옥상':floor+'층');option.value=String(floor);$('floor').append(option);}$('floor').value='7';$('floor').addEventListener('change',draw);
$('mode').addEventListener('change',()=>{const moving=$('mode').value==='moving'&&role==='responder';$('fixed-detail').hidden=moving;$('moving-detail').hidden=!moving;$('path').hidden=moving;$('detail-title').textContent=moving?'가상 주민 이동':'고정 위치의 최신 안내';if(moving)$('person').dispatchEvent(new Event('change'));draw();});
$('person').addEventListener('change',()=>{const p=selectedResident(movement.data,$('person').value);$('person-state').textContent=personDescription();if(p){const n=building.nodes.find(n=>n.id===p.node);if(n)$('floor').value=String(n.floor);}draw();});
$('login-form').addEventListener('submit',async event=>{event.preventDefault();try{const result=await api('/api/v1/session',{method:'POST',body:JSON.stringify({role:$('role').value,access_code:$('code').value})});$('code').value='';$('error').textContent='';await signed(result.role);}catch(error){$('error').textContent=error.message;}});
$('logout').addEventListener('click',async()=>{try{await api('/api/v1/session',{method:'DELETE'});}finally{login();}});
for(const button of document.querySelectorAll('[data-action]'))button.addEventListener('click',async()=>{try{await api('/api/v1/scenario',{method:'POST',body:JSON.stringify({action:button.dataset.action})});render(null);await poll();}catch(error){$('notice').textContent=error.message;}});
setInterval(poll,1500);api('/api/v1/session').then(result=>signed(result.role)).catch(()=>login());
