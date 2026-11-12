import test from 'node:test';
import assert from 'node:assert/strict';
import {routeFor,timeLabel,selectedResident,rememberPeople,peoplePresentation,residentOptionsKey} from '../../frontend/scenario/model.mjs';

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
