import test from 'node:test';
import assert from 'node:assert/strict';
import {zoneBox, zoneLook, describeScene, describeZone, cameraFor, projectPoint, pickBox, crowdPositions, COLORS} from '../../frontend/scenario/building-view.mjs';

/** Same zones and links as mec/risk/evacuation.py Navigation (164 nodes). */
function building() {
  const nodes = [];
  const edges = [];
  const link = (from, to) => edges.push({from, to, length_m: 5});
  for (let floor = 1; floor <= 10; floor += 1) {
    for (let room = 1; room <= (floor === 1 ? 4 : 9); room += 1) nodes.push({id: `F${floor}-R${room}`, kind: 'room', floor});
    if (floor === 1) {
      nodes.push({id: 'F1-L', kind: 'lobby', floor: 1});
      for (const suffix of ['R1', 'R2', 'R3', 'R4', 'SA', 'SB']) link('F1-L', 'F1-' + suffix);
    } else {
      for (let c = 1; c <= 5; c += 1) {
        nodes.push({id: `F${floor}-C${c}`, kind: 'corridor', floor});
        link(`F${floor}-C${c}`, `F${floor}-R${c}`);
        if (c < 5) link(`F${floor}-C${c}`, `F${floor}-C${c + 1}`);
      }
      for (const [c, room] of [[1, 6], [2, 7], [4, 8], [5, 9]]) link(`F${floor}-C${c}`, `F${floor}-R${room}`);
      link(`F${floor}-C1`, `F${floor}-SA`);
      link(`F${floor}-C5`, `F${floor}-SB`);
    }
    for (const [suffix, kind] of [['SA', 'stair'], ['SB', 'stair'], ['E', 'elevator']]) nodes.push({id: `F${floor}-${suffix}`, kind, floor});
    if (floor < 10) for (const side of ['A', 'B']) link(`F${floor}-S${side}`, `F${floor + 1}-S${side}`);
  }
  nodes.push({id: 'F11-ROOF', kind: 'roof', floor: 11}, {id: 'EXIT_A', kind: 'exit', floor: 1}, {id: 'EXIT_B', kind: 'exit', floor: 1});
  link('F1-L', 'EXIT_A');
  link('F1-L', 'EXIT_B');
  return {nodes, edges};
}

const emptyState = {path: [], blocked: new Set(), hazards: new Map(), origin: null, person: null};
const overlapInPlan = (a, b) => Math.abs(a.x - b.x) < (a.width + b.width) / 2 - 1e-6 && Math.abs(a.z - b.z) < (a.depth + b.depth) / 2 - 1e-6;

test('every zone has a box and zones on one floor never overlap', () => {
  const {nodes} = building();
  assert.equal(nodes.length, 164);
  for (let floor = 1; floor <= 10; floor += 1) {
    const boxes = nodes.filter(n => n.floor === floor).map(n => ({id: n.id, ...zoneBox(n)}));
    for (const box of boxes) assert.ok(Number.isFinite(box.x) && box.width > 0 && box.height > 0, box.id);
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) assert.ok(!overlapInPlan(boxes[i], boxes[j]), `${boxes[i].id} overlaps ${boxes[j].id}`);
    }
  }
  const exits = nodes.filter(n => n.kind === 'exit').map(zoneBox);
  const front = Math.max(...nodes.filter(n => n.floor === 1 && n.kind !== 'exit').map(n => { const b = zoneBox(n); return b.z + b.depth / 2; }));
  assert.ok(exits.every(b => b.z - b.depth / 2 > front), 'exits stand outside the front wall');
  assert.ok(zoneBox({id: 'F3-R1', kind: 'room', floor: 3}).y > zoneBox({id: 'F2-R1', kind: 'room', floor: 2}).y);
});

test('zone colour priority is collapsed > blocked > route > fire > smoke > plain', () => {
  const room = {id: 'F5-R2', kind: 'room', floor: 5};
  const hazards = new Map([['F5-R2', {zone_id: 'F5-R2', fire_index: 30, smoke_index: 40, collapsed: false}]]);
  assert.equal(zoneLook(room, emptyState).condition, 'plain');
  assert.equal(zoneLook(room, {...emptyState, hazards: new Map([['F5-R2', {fire_index: 0, smoke_index: 40, collapsed: false}]])}).condition, 'smoke');
  assert.equal(zoneLook(room, {...emptyState, hazards}).condition, 'fire');
  assert.equal(zoneLook(room, {...emptyState, hazards, path: ['F5-R2']}).condition, 'route');
  assert.equal(zoneLook(room, {...emptyState, hazards, path: ['F5-R2'], blocked: new Set(['F5-R2'])}).condition, 'blocked');
  const collapsed = zoneLook(room, {...emptyState, blocked: new Set(['F5-R2']),
    hazards: new Map([['F5-R2', {fire_index: 70, smoke_index: 90, collapsed: true}]])});
  assert.equal(collapsed.condition, 'collapsed');
  assert.ok(collapsed.heightScale < 1);
  assert.deepEqual(zoneLook(room, {...emptyState, blocked: new Set(['F5-R2'])}).color, COLORS.blocked);
});

test('2D draws one floor; 3D draws all floors with see-through floors above the selection', () => {
  const data = building();
  const plan = describeScene(data, emptyState, {mode: '2d', floor: 7});
  const planIds = plan.boxes.filter(b => b.id).map(b => b.id);
  assert.ok(planIds.length === 17 && planIds.every(id => id.startsWith('F7-')));
  const ground = describeScene(data, emptyState, {mode: '2d', floor: 1}).boxes.filter(b => b.id).map(b => b.id);
  assert.ok(ground.includes('EXIT_A') && ground.includes('EXIT_B') && ground.includes('F1-L'));

  const orbit = describeScene(data, emptyState, {mode: '3d', floor: 4});
  const zones = orbit.boxes.filter(b => b.id);
  assert.equal(zones.length, 164);
  const upper = zones.filter(b => /^F(5|6|7|8|9|10|11)-/.test(b.id));
  assert.ok(upper.length > 0 && upper.every(b => b.alpha < 1 && !b.pickable));
  assert.ok(zones.filter(b => b.id.startsWith('F4-')).every(b => b.alpha === 1 && b.pickable));
  assert.ok(orbit.labels.some(l => l.text === '4층' && l.kind.includes('current')));
});

test('route segments follow the path and skip floor changes in the 2D plan', () => {
  const data = building();
  const state = {...emptyState, path: ['F2-R1', 'F2-C1', 'F2-SA', 'F1-SA', 'F1-L', 'EXIT_A']};
  assert.equal(describeScene(data, state, {mode: '3d', floor: 2}).segments.length, 5);
  assert.equal(describeScene(data, state, {mode: '2d', floor: 2}).segments.length, 2);
  assert.equal(describeScene(data, state, {mode: '2d', floor: 1}).segments.length, 2);
});

test('origin and moving-resident markers are labelled', () => {
  const data = building();
  const withOrigin = describeScene(data, {...emptyState, origin: 'F7-R3'}, {mode: '2d', floor: 7});
  assert.ok(withOrigin.labels.some(l => l.kind === 'origin'));
  const person = {node: 'F7-R3', target: 'F7-C3', ratio: 0.5, historical: true};
  const moving = describeScene(data, {...emptyState, person}, {mode: '3d', floor: 7});
  assert.ok(moving.labels.some(l => l.kind === 'person historical'));
  assert.equal(describeScene(data, {...emptyState, person}, {mode: '2d', floor: 6}).labels.filter(l => l.kind.startsWith('person')).length, 0);
});

test('clicking the projected centre of a zone picks that zone in 2D and 3D', () => {
  const data = building();
  for (const mode of ['2d', '3d']) {
    const scene = describeScene(data, emptyState, {mode, floor: 7});
    const camera = cameraFor(mode, 7, 1.6);
    const box = zoneBox({id: 'F7-R3', kind: 'room', floor: 7});
    const point = projectPoint(camera.viewProjection, [box.x, box.y + box.height / 2, box.z], 1600, 1000);
    assert.ok(point, mode);
    const nx = point.x / 1600 * 2 - 1;
    const ny = 1 - point.y / 1000 * 2;
    assert.equal(pickBox(scene, camera.viewProjection, nx, ny), 'F7-R3', mode);
  }
  const camera = cameraFor('3d', 7, 1.6);
  assert.equal(projectPoint(camera.viewProjection, camera.eye.map((v, i) => v + (i === 1 ? 10 : 0)), 100, 100), null);
});

test('crowd is drawn on top of zones, per floor, and counted at the exits', () => {
  const data = building();
  const crowd = [
    {id: 'a', node: 'F7-R3', target: null, ratio: 0, status: 'WAITING'},
    {id: 'b', node: 'F7-R3', target: null, ratio: 0, status: 'QUEUED'},
    {id: 'c', node: 'F7-C3', target: 'F7-C4', ratio: 0.5, status: 'MOVING'},
    {id: 'd', node: 'F3-R1', target: null, ratio: 0, status: 'NO_ROUTE'},
    {id: 'e', node: 'EXIT_A', target: null, ratio: 0, status: 'EVACUATED'},
  ];
  const plan = describeScene(data, {...emptyState, crowd}, {mode: '2d', floor: 7});
  const people = plan.boxes.filter(b => !b.id && b.box.width === 0.7);
  assert.equal(people.length, 3, 'only floor-7 residents in the 2D plan');
  const [first, second] = crowdPositions(new Map(data.nodes.map(n => [n.id, n])), crowd.slice(0, 2)).map(p => p.position);
  assert.notDeepEqual(first, second, 'two people in one room do not overlap');
  const room = zoneBox({id: 'F7-R3', kind: 'room', floor: 7});
  assert.ok(first[1] > room.y + room.height / 2, 'standing residents sit on top of the room box');

  const orbit = describeScene(data, {...emptyState, crowd}, {mode: '3d', floor: 7});
  assert.ok(orbit.labels.some(l => l.text === '7층 · 3명'));
  assert.ok(orbit.labels.some(l => l.text === '3층 · 1명'));
  assert.ok(orbit.labels.some(l => l.text === 'EXIT A · 1명 대피'));
  assert.equal(describeScene(data, {...emptyState, crowd}, {mode: '3d', floor: 2}).boxes.filter(b => !b.id && b.box.width === 0.7).length, 0,
    'residents above the selected floor are hidden in 3D');
});

test('zone description shows hazard numbers only when the view carries them', () => {
  const room = {id: 'F7-R3', kind: 'room', floor: 7};
  assert.match(describeZone(room, emptyState), /구조대 화면에서만/);
  const hazards = new Map([['F7-R3', {fire_index: 12, smoke_index: 30, collapsed: false}]]);
  const text = describeZone(room, {...emptyState, hazards, origin: 'F7-R3'});
  assert.match(text, /화재 12 · 연기 30/);
  assert.match(text, /기준 위치/);
});
