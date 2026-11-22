import test from 'node:test';
import assert from 'node:assert/strict';
import {FrameRecorder, TimelinePlayer, frameEvents, clock} from '../../frontend/scenario/timeline.mjs';

/** A tiny building: two floors of one room, corridor and stair, plus one exit. */
const building = {
  nodes: [
    {id: 'F2-R1', kind: 'room', floor: 2}, {id: 'F2-C1', kind: 'corridor', floor: 2}, {id: 'F2-SA', kind: 'stair', floor: 2},
    {id: 'F1-R1', kind: 'room', floor: 1}, {id: 'F1-L', kind: 'lobby', floor: 1}, {id: 'F1-SA', kind: 'stair', floor: 1},
    {id: 'EXIT_A', kind: 'exit', floor: 1},
  ],
  edges: [
    {from: 'F2-R1', to: 'F2-C1', length_m: 10}, {from: 'F2-C1', to: 'F2-SA', length_m: 10}, {from: 'F2-SA', to: 'F1-SA', length_m: 10},
    {from: 'F1-L', to: 'F1-SA', length_m: 10}, {from: 'F1-L', to: 'F1-R1', length_m: 10}, {from: 'F1-L', to: 'EXIT_A', length_m: 10},
  ],
};

function view(second, {residents, zones = {}, blocked = [], guidance = 'ROUTE_AVAILABLE', exit = 'EXIT_A', ack = 3} = {}) {
  return {
    simulation_second: second, route_version: second + 1, guidance_status: guidance, delivery: {ack_count: ack},
    route: guidance === 'ROUTE_AVAILABLE' ? {target_exit: exit} : null,
    hazards: {blocked_nodes: blocked, zones: Object.entries(zones).map(([zone_id, [fire, smoke, collapsed = false]]) =>
      ({zone_id, fire_index: fire, smoke_index: smoke, collapsed}))},
    residents: residents || [
      {resident_id: 'a', node: 'F2-R1', target: 'F2-C1', progress_m: 2, status: 'MOVING'},
      {resident_id: 'b', node: 'F1-R1', target: null, progress_m: 0, status: 'WAITING'},
    ],
  };
}

function recorder() {
  const result = new FrameRecorder();
  result.setBuilding(building);
  return result;
}

test('records only newer frames and decodes them back', () => {
  const rec = recorder();
  const first = rec.record(view(0, {zones: {'F2-R1': [12, 30]}}), ['F2-R1', 'F2-C1']);
  assert.equal(first.length, 1);
  assert.equal(first[0].kind, 'start');
  assert.equal(rec.record(view(0), []), null, 'same second is skipped');
  assert.ok(rec.record(view(1), []));
  assert.equal(rec.length, 2);
  const frame = rec.decode(0);
  assert.deepEqual(frame.path, ['F2-R1', 'F2-C1']);
  assert.equal(frame.hazards.get('F2-R1').fire_index, 12);
  assert.equal(frame.hazards.get('F2-R1').smoke_index, 30);
  assert.equal(frame.hazards.has('EXIT_A'), false);
  const {ratio, ...first0} = frame.residents[0];
  assert.deepEqual(first0, {id: 'a', node: 'F2-R1', target: 'F2-C1', status: 'MOVING'});
  assert.ok(Math.abs(ratio - 0.2) < 1e-6, 'ratio is stored as Float32');
  assert.equal(frame.counts.MOVING, 1);
  assert.equal(frame.counts.WAITING, 1);
});

test('events describe route, hazard, device, evacuation and stuck changes', () => {
  const rec = recorder();
  rec.record(view(0), ['F2-R1', 'F2-C1', 'EXIT_A']);
  rec.record(view(1), ['F2-R1', 'F2-SA', 'EXIT_A']);
  rec.record(view(2, {exit: 'EXIT_B'}), []);
  rec.record(view(3), []);
  assert.equal(rec.events.filter(e => e.kind === 'route').length, 1, 'quick exit flips are not listed');
  rec.record(view(30, {exit: 'EXIT_B'}), []);
  rec.record(view(31, {guidance: 'NO_VERIFIED_ROUTE'}), []);
  rec.record(view(32, {zones: {'F2-R1': [20, 10]}, blocked: ['F2-R1']}), []);
  rec.record(view(33, {zones: {'F2-R1': [70, 90, true], 'F1-R1': [5, 0]}, blocked: ['F2-R1']}), []);
  rec.record(view(34, {ack: 2}), []);
  rec.record(view(35, {residents: [
    {resident_id: 'a', node: 'EXIT_A', target: null, progress_m: 0, status: 'EVACUATED'},
    {resident_id: 'b', node: 'F1-R1', target: null, progress_m: 0, status: 'NO_ROUTE'}]}), []);
  const kinds = rec.events.map(e => e.kind);
  const texts = rec.events.map(e => e.text).join('\n');
  assert.match(texts, /우회 경로로 변경/);
  assert.match(texts, /출구 변경 EXIT_A → EXIT_B/);
  assert.ok(kinds.includes('noroute'));
  assert.match(texts, /차단 추가: F2-R1/);
  assert.match(texts, /붕괴: F2-R1/);
  assert.match(texts, /2층에서 화재 감지/);
  assert.match(texts, /1층으로 화재 확산/);
  assert.match(texts, /표시 장치 응답 2\/3/);
  assert.match(texts, /표시 장치 응답 3\/3 회복/);
  assert.match(texts, /첫 대피 완료/);
  assert.match(texts, /대피 완료 50% \(1\/2명\)/);
  assert.match(texts, /경로 없음·고립 주민 발생 \(1명\)/);
  assert.equal(rec.events.find(e => e.kind === 'blocked').floor, 2);
  assert.equal(frameEvents(null, rec.frames[0], rec.ids)[0].kind, 'start');
});

test('residents glide between close frames and snap across large gaps', () => {
  const rec = recorder();
  rec.record(view(10, {residents: [{resident_id: 'a', node: 'F2-R1', target: 'F2-C1', progress_m: 2, status: 'MOVING'}]}), []);
  rec.record(view(11, {residents: [{resident_id: 'a', node: 'F2-R1', target: 'F2-C1', progress_m: 6, status: 'MOVING'}]}), []);
  rec.record(view(12, {residents: [{resident_id: 'a', node: 'F2-C1', target: null, progress_m: 0, status: 'WAITING'}]}), []);
  rec.record(view(40, {residents: [{resident_id: 'a', node: 'F1-L', target: null, progress_m: 0, status: 'QUEUED'}]}), []);
  assert.ok(Math.abs(rec.sample(10.5).residents[0].ratio - 0.4) < 1e-6);
  const arriving = rec.sample(11.5).residents[0];
  assert.equal(arriving.target, 'F2-C1');
  assert.ok(Math.abs(arriving.ratio - 0.8) < 1e-6, 'walks on to the end of the link');
  assert.equal(rec.sample(30).residents[0].node, 'F2-C1', 'no gliding across a 28 s gap');
  assert.equal(rec.sample(99).second, 40, 'clamped to the recording');
  assert.equal(rec.sample(0).second, 10);
});

test('player plays, steps, seeks and returns to live at the end', () => {
  const rec = recorder();
  for (const second of [0, 1, 2, 5]) rec.record(view(second), []);
  const player = new TimelinePlayer();
  assert.equal(player.position(rec), 5);
  player.play(rec);
  assert.ok(player.playing && !player.live);
  assert.equal(player.position(rec), 0);
  player.speed = 2;
  player.tick(0.5, rec);
  assert.equal(player.position(rec), 1);
  player.step(1, rec);
  assert.equal(player.position(rec), 2);
  assert.equal(player.playing, false);
  player.step(-1, rec);
  assert.equal(player.position(rec), 1);
  player.seek(-10, rec);
  assert.equal(player.position(rec), 0);
  player.play(rec);
  player.tick(10, rec);
  assert.ok(player.live && !player.playing, 'catching up with the newest frame goes live');
});

test('old frames are dropped past the limit and clock formats mm:ss', () => {
  const rec = new FrameRecorder(3);
  rec.setBuilding(building);
  for (let second = 0; second < 6; second += 1) rec.record(view(second, {ack: second % 2 ? 2 : 3}), []);
  assert.equal(rec.length, 3);
  assert.equal(rec.firstSecond, 3);
  assert.ok(rec.events.every(e => e.second >= 3));
  assert.equal(clock(754), '12:34');
  assert.equal(clock(undefined), '00:00');
});
