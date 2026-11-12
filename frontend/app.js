import {guidance, accepts} from '/model.mjs';
const $=id=>document.getElementById(id);
let role=null,mode='resident',incident=null,building=null,previous=null,refreshing=false;
const labels={F3_ROOM1:'3F · ROOM 1',F3_C:'3F · 복도',F3_A:'3F · A 계단',F3_B:'3F · B 계단',F2_A:'2F · A 계단',F2_B:'2F · B 계단',F1_A:'1F · A 계단',F1_B:'1F · B 계단',EXIT_A:'출구 A',EXIT_B:'출구 B'};
function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
function svg(tag,attrs){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);return el;}
async function api(path,options={}){
  const response=await fetch(path,{...options,cache:'no-store',headers:{'Content-Type':'application/json',...(options.headers||{})}});
  let body;try{body=await response.json();}catch{throw new Error('응답을 확인할 수 없습니다.');}
  if(response.status===401){showLogin();throw new Error('역할과 접속 코드를 확인하세요.');}
  if(!response.ok){const error=new Error(response.status===409?'이전 시나리오를 처리하고 있습니다.':response.status===403?'이 역할로는 사용할 수 없습니다.':'현재 상태를 확인할 수 없습니다.');error.body=body;throw error;}
  return body;
}
function showLogin(){role=null;previous=null;$('dashboard').hidden=true;$('login-screen').hidden=false;}
async function signedIn(value){role=value;mode=role==='responder'?'responder':'resident';$('login-screen').hidden=true;$('dashboard').hidden=false;$('responder-tab').hidden=role!=='responder';$('role-label').textContent=role==='responder'?'구조대':'주민';building=await api('/api/v1/building');setMode(mode);}
function setMode(value){mode=value;previous=null;const responder=mode==='responder';$('view-title').textContent=responder?'구조대 상황판':'주민 대피 안내';$('page-title').textContent=responder?'화재 대응 상황판':'대피 경로 안내';$('page-description').textContent=responder?'위험 구역과 안내 장치 응답, 합성 잔류자 정보를 확인하세요.':'현재 확인된 경로와 안내 장치의 전달 상태를 확인하세요.';$('responder-content').hidden=!responder;$('resident-tab').classList.toggle('active',!responder);$('responder-tab').classList.toggle('active',responder);poll();}
function drawMap(view,model){
  const root=$('building-map');root.replaceChildren();if(!building)return;
  const coords={};for(const n of building.nodes){coords[n.id]=[n.id.endsWith('_A')||n.id==='EXIT_A'?125:n.id.endsWith('_B')||n.id==='EXIT_B'?575:350,n.kind==='room'?38:90+(3-n.floor)*110];}
  for(let floor=3;floor>=0;floor--){const y=90+(3-floor)*110;root.append(svg('rect',{x:55,y:y-35,width:590,height:72,rx:14,class:'floor-band'}));const text=svg('text',{x:15,y:y+5,class:'floor-label'});text.textContent=floor?floor+'F':'G';root.append(text);}
  const blocked=new Set(view?.hazards?.blocked_nodes||[]);const pathEdges=new Set(model.path.slice(1).flatMap((n,i)=>[model.path[i]+'|'+n,n+'|'+model.path[i]]));
  for(const e of building.edges){const a=coords[e.from],b=coords[e.to];root.append(svg('line',{x1:a[0],y1:a[1],x2:b[0],y2:b[1],class:pathEdges.has(e.from+'|'+e.to)?'map-edge selected':'map-edge'}));}
  for(const n of building.nodes){const [x,y]=coords[n.id];const selected=model.path.includes(n.id);const group=svg('g',{class:'map-node'+(blocked.has(n.id)?' blocked':selected?' selected':'')});group.append(svg('circle',{cx:x,cy:y,r:n.kind==='exit'?18:11}));const text=svg('text',{x,y:y+(n.kind==='room'?-19:31),'text-anchor':'middle'});text.textContent=labels[n.id]||n.id;group.append(text);if(n.kind==='exit'){const arrow=svg('text',{x,y:y+6,'text-anchor':'middle',class:'exit-arrow'});arrow.textContent='↗';group.append(arrow);}root.append(group);}
}
function render(view){
  const model=guidance(view,incident);const live=view?.connections?.cse==='LIVE';$('connection-dot').className='dot '+(live?'live':'offline');$('connection-label').textContent=live?'실제 CSE 응답 확인':'CSE 연결 확인 필요';
  $('updated').textContent=view?.observed_at_utc?'관측 '+new Date(view.observed_at_utc).toLocaleTimeString('ko-KR'):'관측 정보 대기';
  $('guidance-value').textContent=model.label;$('guidance-detail').textContent=model.status==='STALE'?'오래된 방향을 표시하지 않습니다.':'현재 CSE 기록 기준';$('exit-value').textContent=model.exit?labels[model.exit]:'—';$('route-exit').textContent=model.exit?model.exit.replace('_',' '):'—';
  const count=view?.delivery?.ack_count;$('ack-value').replaceChildren(node('span',Number.isInteger(count)?String(count):'—'),node('em',' / 3'));
  $('delivery-value').textContent=view?.delivery?.state==='ALL_ACKED'?'모든 장치 적용 확인':model.incomplete?'일부 장치 응답 없음':'전달 상태 확인 중';$('version-value').textContent=Number.isInteger(view?.route_version)?'v'+view.route_version:'—';$('incident-value').textContent=incident?incident.slice(0,16):'사건 정보 대기';
  $('map-status').textContent=model.label;$('map-status').className='pill '+(model.status==='ROUTE_AVAILABLE'?'green':model.status==='NO_VERIFIED_ROUTE'?'red':'neutral');
  const messages={ROUTE_AVAILABLE:model.incomplete?'계산된 경로는 확인됐지만 일부 안내 장치가 응답하지 않았습니다.':'현재 계산 경로와 장치 적용 상태를 확인했습니다.',NO_VERIFIED_ROUTE:'현재 합성 그래프에서 확인된 대피 경로가 없습니다. 이전 방향을 제거했습니다.',STALE:'센서 관측이 만료됐습니다. 오래된 방향 안내를 숨깁니다.',PENDING:'새 관측과 장치 응답을 대조하고 있습니다. 방향 안내를 기다려 주세요.',UNKNOWN:'현재 경로를 확인할 수 없습니다. 연결 상태와 관측을 확인하세요.'};
  $('notice').textContent=messages[model.status];$('notice').className='notice '+(model.status==='ROUTE_AVAILABLE'&&!model.incomplete?'ok':model.status==='NO_VERIFIED_ROUTE'?'danger':'');$('route-message').textContent=model.exit?'출발 지점에서 '+labels[model.exit]+'까지의 모의 경로입니다.':messages[model.status];
  $('route-steps').replaceChildren(...model.path.map(n=>node('li',labels[n]||n)));drawMap(view,model);
  if(mode==='responder')renderDiagnostics(view);
}
function renderDiagnostics(view){
  $('devices').replaceChildren(...(view?.devices||[]).map(d=>{const el=node('article',undefined,'device-card');el.append(node('span',d.device.toUpperCase()),node('strong',d.status==='APPLIED'?'적용 확인':d.status==='STALE'?'마지막 ACK 만료':d.status==='UNKNOWN'?'확인 불가':'응답 없음',d.status==='APPLIED'?'text-green':'text-red'),node('small',d.ack_timestamp_utc?new Date(d.ack_timestamp_utc).toLocaleTimeString('ko-KR'):'현재 명령 ACK 없음'));return el;}));
  const blocks=view?.hazards?.blocked_nodes||[];$('hazards').replaceChildren(...(blocks.length?blocks.map(n=>node('span',labels[n]||n,'pill red')):[node('span',view?.hazards?'관측된 차단 구역 없음':'위험 구역 정보 확인 불가','pill neutral')]));
  const table=node('table');const head=node('tr');for(const t of ['센서 / 지점','관측 값','입력'])head.append(node('th',t));table.append(head);
  for(const s of view?.sensors||[]){const row=node('tr');row.append(node('td',labels[s.location_node]||s.location_node),node('td',s.value+(s.unit==='degC'?' °C':' / 100')),node('td','SYNTHETIC'));table.append(row);}$('sensors').replaceChildren(table);
  const occupants=(view?.occupants||[]).map(o=>{const el=node('article',undefined,'occupant');el.append(node('b',labels[o.zone_id]||o.zone_id),node('strong',o.status==='KNOWN'?o.remaining_count+' 명':'UNKNOWN'),node('small','합성 관측 · '+new Date(o.timestamp_utc).toLocaleTimeString('ko-KR')));return el;});
  $('occupants').replaceChildren(...(occupants.length?occupants:[node('p','잔류자 정보 UNKNOWN')]));
}
async function poll(){
  if(!role||refreshing)return;refreshing=true;
  try{const status=await api('/api/v1/status');incident=status.incident_id;for(const b of document.querySelectorAll('[data-action]'))b.disabled=status.busy;if(!incident){render(null);return;}const view=await api('/api/v1/incidents/'+encodeURIComponent(incident)+'/'+mode);if(accepts(previous,view)){if(!previous||previous.incident_id!==view.incident_id||Number.isInteger(view.route_version)&&view.route_version>=(previous.route_version||0))previous=view;render(view);}}
  catch(error){render(error.body?.guidance_status?error.body:null);}
  finally{refreshing=false;}
}
$('login-form').addEventListener('submit',async event=>{event.preventDefault();$('login-error').textContent='';try{const reply=await api('/api/v1/session',{method:'POST',body:JSON.stringify({role:$('role').value,access_code:$('access-code').value})});$('access-code').value='';await signedIn(reply.role);}catch(error){$('login-error').textContent=error.message;}});
$('logout').addEventListener('click',async()=>{try{await api('/api/v1/session',{method:'DELETE'});}finally{showLogin();}});
$('resident-tab').addEventListener('click',()=>setMode('resident'));$('responder-tab').addEventListener('click',()=>{if(role==='responder')setMode('responder');});
for(const button of document.querySelectorAll('[data-action]'))button.addEventListener('click',async()=>{try{await api('/api/v1/scenario',{method:'POST',body:JSON.stringify({action:button.dataset.action})});$('action-message').textContent='실제 CSE 처리와 장치 응답을 확인하고 있습니다.';render(null);await poll();}catch(error){$('action-message').textContent=error.message;}});
setInterval(poll,2000);
api('/api/v1/session').then(x=>signedIn(x.role)).catch(()=>showLogin());
