export function guidance(view, currentIncident) {
  const labels={ROUTE_AVAILABLE:'경로 확인',NO_VERIFIED_ROUTE:'경로 없음',STALE:'정보 만료',UNKNOWN:'확인 불가',PENDING:'갱신 중'};
  const valid=view && view.incident_id===currentIncident && view.connections?.cse==='LIVE';
  const status=valid ? (Object.hasOwn(labels,view.guidance_status) ? view.guidance_status:'UNKNOWN'):'UNKNOWN';
  const available=status==='ROUTE_AVAILABLE' && view.route && Array.isArray(view.route.path) && view.route.path.length>0 && typeof view.route.target_exit==='string';
  return {status: available ? status : status==='ROUTE_AVAILABLE'?'UNKNOWN':status,
    label:labels[available ? status : status==='ROUTE_AVAILABLE'?'UNKNOWN':status],
    exit:available?view.route.target_exit:null,path:available?view.route.path:[],
    incomplete:view?.delivery?.state==='INCOMPLETE'};
}

export function accepts(previous,next) {
  return next.guidance_status!=='ROUTE_AVAILABLE' || !previous || previous.incident_id!==next.incident_id ||
    !Number.isInteger(previous.route_version) || !Number.isInteger(next.route_version) || next.route_version>=previous.route_version;
}
