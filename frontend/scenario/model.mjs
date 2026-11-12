export function routeFor(view){
  return view?.connections?.cse==='LIVE'&&view.guidance_status==='ROUTE_AVAILABLE'&&Array.isArray(view.route?.path)&&view.route.path.length?view.route.path:[];
}
export function timeLabel(seconds){return Number.isInteger(seconds)?`${Math.floor(seconds/60)}분 ${seconds%60}초`:'—';}
export function selectedResident(view,id){return view?.residents?.find(p=>p.resident_id===id)||view?.residents?.[0]||null;}

function hasPeople(data,incident){
  return Boolean(incident&&data?.incident_id===incident&&Number.isInteger(data.route_version)&&data.route_version>0
    &&Array.isArray(data.residents)&&data.population&&Number.isInteger(data.population.total)
    &&data.residents.length===data.population.total);
}
export function freshPeople(data,incident){
  return hasPeople(data,incident)&&data.is_live!==false&&data.connections?.cse==='LIVE'
    &&['ROUTE_AVAILABLE','NO_VERIFIED_ROUTE'].includes(data.guidance_status);
}
function acceptedRecord(data,incident){
  return freshPeople(data,incident)||(hasPeople(data,incident)&&data.snapshot_kind==='HISTORICAL'&&data.is_live===false);
}
export function rememberPeople(previous,incoming,incident){
  const old=acceptedRecord(previous,incident)?previous:null;
  if(!acceptedRecord(incoming,incident))return old;
  return !old||incoming.route_version>=old.route_version?incoming:old;
}
export function peoplePresentation(live,saved,incident){
  if(freshPeople(live,incident))return {kind:'LIVE',data:live};
  if(acceptedRecord(saved,incident))return {kind:'HISTORICAL',data:saved};
  return {kind:'UNAVAILABLE',data:null};
}
export function residentOptionsKey(data){return (data?.residents||[]).map(p=>p.resident_id).join('\u0000');}
