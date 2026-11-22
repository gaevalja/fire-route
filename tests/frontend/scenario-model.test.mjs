import test from 'node:test';
import assert from 'node:assert/strict';
import {routeFor,timeLabel,selectedResident,rememberPeople,peoplePresentation,residentOptionsKey,mecLabel,zoneRouteFor,zoneSummary,roomOptions,estimatePresentation} from '../../frontend/scenario/model.mjs';

test('room guidance shows only a live correlated route for the chosen room',()=>{
  const live={connections:{cse:'LIVE'},guidance_status:'ROUTE_AVAILABLE',
    zone_route:{source_node:'F5-R2',status:'ROUTE_AVAILABLE',target_exit:'EXIT_A',path:['F5-R2','F5-C2','EXIT_A']}};
  assert.deepEqual(zoneRouteFor(live,'F5-R2'),live.zone_route.path);
  assert.deepEqual(zoneRouteFor(live,'F9-R1'),[]);
  assert.deepEqual(zoneRouteFor(live,''),[]);
  for(const state of ['STALE','PENDING','UNKNOWN'])assert.deepEqual(zoneRouteFor({...live,guidance_status:state},'F5-R2'),[]);
  assert.equal(zoneSummary({...live,guidance_status:'STALE'},'F5-R2').state,'UNAVAILABLE');
  assert.equal(zoneSummary(live,'F5-R2').state,'ROUTE');
  assert.equal(zoneSummary({...live,zone_route:{source_node:'F5-R2',status:'NO_VERIFIED_ROUTE',target_exit:null,path:[]}},'F5-R2').state,'NO_ROUTE');
  assert.equal(zoneSummary(live,''),null);
});
test('room picker lists rooms by floor in numeric order',()=>{
  const groups=roomOptions({nodes:[{id:'F2-R10',kind:'room',floor:2},{id:'F2-R2',kind:'room',floor:2},{id:'F1-L',kind:'lobby',floor:1},{id:'F1-R1',kind:'room',floor:1}]});
  assert.deepEqual(groups,[{floor:1,rooms:['F1-R1']},{floor:2,rooms:['F2-R2','F2-R10']}]);
});
test('occupancy estimate never shows a stale or missing estimate as current',()=>{
  assert.equal(estimatePresentation({}).state,'UNAVAILABLE');
  assert.equal(estimatePresentation({occupancy_estimate:{state:'UNKNOWN'}}).rows.length,0);
  const shown=estimatePresentation({occupancy_estimate:{state:'ESTIMATED',estimated_remaining:3,registered_prior_total:8,detected_exits:5,presence_scans:4,
    evaluation:{truth_zones:2,detected_zones:1,missed_zones:1,false_zones:1,count_abs_error:2,high_zones:1,high_true_zones:1,
                possible_zones:1,possible_true_zones:0,low_zones:1,low_true_zones:0},
    priority:[{rank:1,zone_id:'F7-R3',estimated_count:2,likelihood:'HIGH',probability:0.964,last_detection_second:null,basis:'REGISTERED_PRIOR',
               evidence:{access_count:2,scans:0,detections:0},hazard:{blocked:true}},
              {rank:2,zone_id:'F5-C2',estimated_count:1,likelihood:'POSSIBLE',probability:0.68,last_detection_second:61,basis:'PRESENCE_SCAN',
               evidence:{access_count:0,scans:1,detections:1},hazard:{fire_index:30,smoke_index:5}},
              {rank:3,zone_id:'F3-R1',estimated_count:1,likelihood:'LOW',probability:0.29,last_detection_second:12,basis:'PASSAGE',
               evidence:{access_count:1,scans:3,detections:0},hazard:{}}]}});
  assert.equal(shown.rows[0].hazard,'차단');assert.equal(shown.rows[0].count,'추정 2명');assert.equal(shown.rows[0].probability,'96%');
  assert.equal(shown.rows[1].last,'1분 1초');assert.equal(shown.rows[1].hazard,'위험 지수 30');
  assert.equal(shown.rows[1].basis,'스캔만 감지 · 스캔 1/1회 감지');assert.equal(shown.rows[2].likelihood,'낮음');
  assert.match(shown.summary,/미탐 1/);assert.match(shown.summary,/높음 1 · 있음 1 · 낮음 1/);
  assert.match(shown.summary,/등록 8 − 출구 통과 감지 5/);assert.match(shown.summary,/스캔 4회 반영/);
});

test('selected profile hides directions for stale pending and failed CSE',()=>{
  const current={connections:{cse:'LIVE'},guidance_status:'ROUTE_AVAILABLE',route:{path:['F7-R3','EXIT_A']}};
  assert.deepEqual(routeFor(current),current.route.path);
  for(const state of ['STALE','PENDING','UNKNOWN','NO_VERIFIED_ROUTE'])assert.deepEqual(routeFor({...current,guidance_status:state}),[]);
  assert.deepEqual(routeFor({...current,connections:{cse:'UNAVAILABLE'}}),[]);
});
test('missing private data cannot fabricate resident positions',()=>{
  assert.equal(selectedResident({},'person'),null);
  assert.equal(selectedResident({residents:[]},'person'),null);
  const p={resident_id:'unit',node:'F7-R3'};
  assert.equal(selectedResident({residents:[p]},'unit'),p);
});
test('simulation clock keeps seconds distinct from wall clock',()=>{
  assert.equal(timeLabel(61),'1분 1초');assert.equal(timeLabel(null),'—');
});

function current(version=1,incident='inc-unit'){
  return {incident_id:incident,route_version:version,simulation_second:version-1,
    connections:{cse:'LIVE'},guidance_status:'ROUTE_AVAILABLE',population:{total:2},
    residents:[{resident_id:'p1',node:'F7-R3'},{resident_id:'p2',node:'F8-R1'}],
    observed_at_utc:'2026-11-12T00:00:00Z',route:{path:['F7-R3','EXIT_A']}};
}
test('pause expiry and update gaps retain selectable people as historical only',()=>{
  const data=current(),saved=rememberPeople(null,data,'inc-unit');
  for(const state of ['STALE','PENDING','UNKNOWN']){
    const live={incident_id:'inc-unit',guidance_status:state};
    const display=peoplePresentation(live,saved,'inc-unit');
    assert.equal(display.kind,'HISTORICAL');assert.equal(selectedResident(display.data,'p2').node,'F8-R1');
    assert.deepEqual(routeFor(live),[]);
  }
  assert.equal(peoplePresentation(data,saved,'inc-unit').kind,'LIVE');
});
test('first visit after expiry accepts explicitly historical backend snapshot',()=>{
  const snapshot={...current(),snapshot_kind:'HISTORICAL',is_live:false,guidance_status:'HISTORICAL',route:null};
  const saved=rememberPeople(null,snapshot,'inc-unit');
  assert.equal(peoplePresentation(null,saved,'inc-unit').kind,'HISTORICAL');
  assert.equal(saved.residents.length,2);assert.deepEqual(routeFor(snapshot),[]);
});
test('logout reset and another incident cannot reuse private selection data',()=>{
  const saved=current();
  assert.equal(rememberPeople(saved,null,null),null);
  assert.equal(peoplePresentation(null,saved,'different-incident').kind,'UNAVAILABLE');
  assert.equal(rememberPeople(saved,null,'different-incident'),null);
});
test('older snapshots cannot overwrite a newer selection frame',()=>{
  const saved=current(3);
  assert.equal(rememberPeople(saved,current(1),'inc-unit'),saved);
  assert.equal(rememberPeople(saved,current(4),'inc-unit').route_version,4);
  assert.equal(rememberPeople(saved,{...current(5),guidance_status:'PENDING'},'inc-unit'),saved);
});
test('stable IDs keep the options key constant while positions update',()=>{
  const a=current(1),b=current(2);b.residents[0].node='F7-C3';
  assert.equal(residentOptionsKey(a),residentOptionsKey(b));
  b.residents.push({resident_id:'p3'});assert.notEqual(residentOptionsKey(a),residentOptionsKey(b));
});
test('absent data stays unavailable rather than inventing people',()=>{
  assert.equal(peoplePresentation({guidance_status:'STALE'},null,'inc-unit').kind,'UNAVAILABLE');
  const malformed={...current(),population:{total:3}};
  assert.equal(rememberPeople(null,malformed,'inc-unit'),null);
});
test('MEC badge requires a verified current result rather than only configuration or a running service',()=>{
  assert.equal(mecLabel(null),'MEC 미연결');
  const view={connections:{cse:'LIVE',mec:'VERIFIED_RESULT'},guidance_status:'ROUTE_AVAILABLE'};
  assert.equal(mecLabel(view),'MEC 경유 계산 확인');
  assert.equal(mecLabel({...view,guidance_status:'NO_VERIFIED_ROUTE'}),'MEC 경유 계산 확인');
  for(const status of ['STALE','UNKNOWN','PENDING'])assert.notEqual(mecLabel({...view,guidance_status:status}),'MEC 경유 계산 확인');
  assert.notEqual(mecLabel({...view,connections:{cse:'UNKNOWN',mec:'VERIFIED_RESULT'}}),'MEC 경유 계산 확인');
});
