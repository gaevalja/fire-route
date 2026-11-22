/**
 * WebGL building view for the FireRoute scenario dashboard.
 *
 * Shows the synthetic ten-floor building either in 3D (orbit camera, upper floors see-through)
 * or as a 2D top-down plan of one floor. The layout is the same assumed schematic used by the
 * route model; it is not a surveyed floor plan.
 *
 * The pure helpers (layout, colours, scene description, picking) never touch the DOM, so they
 * run in Node unit tests. Only the BuildingView class uses WebGL. There are no external
 * libraries because the dashboard's Content-Security-Policy allows scripts from 'self' only.
 */

// ---------------------------------------------------------------------------------------------
// Layout (assumed metres; x = left/right, y = up, z = back(-)/front(+), exits are at the front)
// ---------------------------------------------------------------------------------------------

export const FLOOR_HEIGHT = 3.2;
import './locale.js';
const {t} = globalThis.FireRouteLocale;

const SLAB_THICKNESS = 0.18;
const COLUMN_SPACING = 6;
const ROOM_SIZE = {width: 5.4, depth: 5, height: 2.4};
const ROW_Z = {back: -5.5, middle: 0, front: 5.5};
const CORRIDOR_DEPTH = 2.6;
const FLAT_HEIGHT = 0.3;
const FOOTPRINT = {width: 41.2, depth: 16.6};
/** Rooms 6–9 sit in the front row under corridor columns 1, 2, 4 and 5 (column 3 is the elevator). */
const FRONT_ROOM_COLUMN = {6: 1, 7: 2, 8: 4, 9: 5};

const columnX = column => (column - 3) * COLUMN_SPACING;
const floorBase = floor => (floor - 1) * FLOOR_HEIGHT;
const suffixNumber = (id, marker) => Number(id.split(marker)[1]);

/** Axis-aligned box of one zone: centre (x, y, z) and size (width, height, depth). */
export function zoneBox(node) {
  const base = floorBase(node.floor);
  const box = (x, z, width, depth, height) => ({x, y: base + height / 2, z, width, height, depth});
  switch (node.kind) {
    case 'room': {
      const number = suffixNumber(node.id, '-R');
      const back = number <= 5;
      const column = back ? number : FRONT_ROOM_COLUMN[number];
      return box(columnX(column), back ? ROW_Z.back : ROW_Z.front, ROOM_SIZE.width, ROOM_SIZE.depth, ROOM_SIZE.height);
    }
    case 'corridor':
      return box(columnX(suffixNumber(node.id, '-C')), ROW_Z.middle, COLUMN_SPACING - 0.06, CORRIDOR_DEPTH, FLAT_HEIGHT);
    case 'lobby':
      return box(0, ROW_Z.middle, COLUMN_SPACING * 5 - 0.06, CORRIDOR_DEPTH, FLAT_HEIGHT);
    case 'stair':
      return box(node.id.endsWith('SA') ? -18 : 18, ROW_Z.middle, 4.6, 5, FLOOR_HEIGHT - SLAB_THICKNESS);
    case 'elevator':
      return box(0, ROW_Z.front - 0.5, 3, 3.6, FLOOR_HEIGHT - SLAB_THICKNESS);
    case 'roof':
      return box(0, 0, FOOTPRINT.width - 0.4, FOOTPRINT.depth - 0.4, FLAT_HEIGHT);
    case 'exit':
      return box(node.id === 'EXIT_A' ? -6 : 6, 9.8, 3.4, 2.2, FLAT_HEIGHT);
    default:
      return null;
  }
}

/** Point where route lines and people attach to a zone. */
export function zoneAnchor(node) {
  const box = zoneBox(node);
  return [box.x, floorBase(node.floor) + 0.9, box.z];
}

function floorSlab(floor) {
  const base = floorBase(floor);
  return {x: 0, y: base - SLAB_THICKNESS / 2, z: 0, width: FOOTPRINT.width, height: SLAB_THICKNESS, depth: FOOTPRINT.depth};
}

const KIND_NAMES = {room: ['방', 'Room'], corridor: ['복도', 'Corridor'], lobby: ['로비', 'Lobby'], stair: ['계단', 'Stairs'],
  elevator: ['엘리베이터 (대피 불가)', 'Elevator (unavailable for evacuation)'], roof: ['옥상 (대피 공간)', 'Roof (refuge area)'], exit: ['출구', 'Exit']};

/** Short on-screen name: "R3", "C2", "SA", "로비", "EXIT A". */
export function shortName(node) {
  if (node.kind === 'exit') return node.id.replace('_', ' ');
  if (node.kind === 'lobby') return t('로비', 'Lobby');
  if (node.kind === 'roof') return t('옥상', 'Roof');
  return node.id.split('-')[1] || node.id;
}

const floorName = floor => floor === 11 ? t('옥상층', 'Roof') : t(`${floor}층`, `Floor ${floor}`);
/** Floors above the selected one in 3D: barely-there fill and faint edges, so the selected floor stays readable. */
const GHOST = {alpha: 0.045, outlineAlpha: 0.12};

// ---------------------------------------------------------------------------------------------
// Colours
// ---------------------------------------------------------------------------------------------

export const COLORS = {
  room: [0.88, 0.91, 0.94], corridor: [0.78, 0.83, 0.87], lobby: [0.77, 0.86, 0.82], stair: [0.71, 0.78, 0.95],
  elevator: [0.84, 0.81, 0.91], roof: [0.86, 0.92, 0.84], exit: [0.11, 0.61, 0.45], slab: [0.95, 0.96, 0.97],
  route: [0.20, 0.71, 0.49], fireLow: [0.99, 0.82, 0.64], fireHigh: [0.92, 0.42, 0.16], smoke: [0.52, 0.55, 0.60],
  blocked: [0.84, 0.25, 0.27], collapsed: [0.42, 0.11, 0.12], origin: [0.16, 0.48, 0.87], person: [0.16, 0.48, 0.87],
  historical: [0.78, 0.54, 0.17], outline: [0.33, 0.41, 0.48], routeLine: [0.07, 0.55, 0.36],
};

/** Resident states from simulator/evacuation.py, with the colour used on the map, chart and legend. */
export const RESIDENT_STATES = {
  MOVING: {label: '이동 중', english: 'Moving', color: '#2f7de1'},
  QUEUED: {label: '통로 정체', english: 'Queued', color: '#f0a020'},
  WAITING: {label: '출발 전 대기', english: 'Awaiting departure', color: '#8a9bab'},
  NO_ROUTE: {label: '경로 없음', english: 'No route', color: '#e2553e'},
  BLOCKED_IN_TRANSIT: {label: '이동 중 고립', english: 'Blocked in transit', color: '#9b1f2a'},
  EVACUATED: {label: '대피 완료', english: 'Evacuated', color: '#1f9d6b'},
};
const PERSON_SIZE = {width: 0.7, height: 1.2};
const hexToRgb = hex => [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);

const mix = (a, b, t) => a.map((value, i) => value + (b[i] - value) * t);
const clamp01 = value => Math.min(1, Math.max(0, value));
const onRoute = (state, id) => (state.routeNodes ? state.routeNodes.has(id) : (state.path || []).includes(id));

/**
 * How one zone looks this frame. Priority: collapsed > blocked > on the route > fire > smoke > plain.
 * Returns the colour, a height multiplier (collapsed zones are drawn flattened) and the state name.
 */
export function zoneLook(node, state) {
  const hazard = state.hazards?.get(node.id);
  if (node.kind === 'exit') return {color: COLORS.exit, heightScale: 1, condition: 'exit'};
  if (hazard?.collapsed) return {color: COLORS.collapsed, heightScale: 0.35, condition: 'collapsed'};
  if (state.blocked?.has(node.id)) return {color: COLORS.blocked, heightScale: 1, condition: 'blocked'};
  if (onRoute(state, node.id)) return {color: COLORS.route, heightScale: 1, condition: 'route'};
  const base = COLORS[node.kind] || COLORS.room;
  if (hazard?.fire_index > 0) {
    const t = clamp01(hazard.fire_index / 60);
    return {color: mix(COLORS.fireLow, COLORS.fireHigh, t), heightScale: 1, condition: 'fire'};
  }
  if (hazard?.smoke_index > 0) {
    const t = clamp01(hazard.smoke_index / 80) * 0.75;
    return {color: mix(base, COLORS.smoke, t), heightScale: 1, condition: 'smoke'};
  }
  return {color: base, heightScale: 1, condition: 'plain'};
}

const CONDITION_TEXT = {collapsed: ['붕괴','Collapsed'], blocked: ['차단','Blocked'], route: ['계산 경로 포함','On the calculated route'],
  fire: ['화재','Fire'], smoke: ['연기','Smoke'], plain: ['이상 없음','Clear'], exit: ['건물 출구','Building exit']};

/** One-line description shown when a zone is clicked. Hazard numbers appear only when the view carries them. */
export function describeZone(node, state) {
  const parts = [node.id, t(...(KIND_NAMES[node.kind] || [node.kind,node.kind])), floorName(node.floor)];
  const hazard = state.hazards?.get(node.id);
  if (hazard) parts.push(t(`화재 ${hazard.fire_index} · 연기 ${hazard.smoke_index}`,`Fire ${hazard.fire_index} · Smoke ${hazard.smoke_index}`));
  else if (node.kind !== 'exit') parts.push(state.hazards?.size ? t('위험 기록 없음','No hazard record') : t('위험 지수는 구조대 화면에서만 표시','Hazard indices are available in the responder view'));
  parts.push(t(...CONDITION_TEXT[zoneLook(node, state).condition]));
  if (node.id === state.origin) parts.push(t('기준 위치','Origin'));
  return parts.join(' · ');
}

// ---------------------------------------------------------------------------------------------
// Scene description (what to draw), independent of WebGL
// ---------------------------------------------------------------------------------------------

const zoneTop = node => { const box = zoneBox(node); return box.y + box.height / 2; };

/** Small stable number from a resident id, used to spread people sideways on a link. */
function hashOf(text) {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i += 1) { hash ^= text.charCodeAt(i); hash = Math.imul(hash, 16777619); }
  return hash >>> 0;
}

/**
 * Where to draw each resident who is still inside (plus the selected one, even after leaving).
 *
 * People standing in a zone are spread on a small grid on top of it, so they are never hidden inside
 * a solid room. People walking a link sit on the line between the two zones, nudged sideways by a
 * per-person offset so a queue does not collapse into a single dot.
 *
 * crowd: [{id, node, target, ratio, status, selected?}]. Returns [{person, floor, position}].
 */
export function crowdPositions(nodes, crowd) {
  const shown = person => person.status !== 'EVACUATED' || person.selected;
  const standing = new Map();
  for (const person of crowd) {
    if (person.target || !shown(person)) continue;
    if (!standing.has(person.node)) standing.set(person.node, []);
    standing.get(person.node).push(person);
  }
  const placed = [];
  for (const [nodeId, people] of standing) {
    const node = nodes.get(nodeId);
    if (!node) continue;
    const box = zoneBox(node);
    const columns = Math.ceil(Math.sqrt(people.length));
    const rows = Math.ceil(people.length / columns);
    const stepX = Math.min(0.95, (box.width - 0.6) / columns);
    const stepZ = Math.min(0.95, (box.depth - 0.6) / rows);
    people.sort((a, b) => (a.id < b.id ? -1 : 1));
    people.forEach((person, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      placed.push({person, floor: node.floor, position: [
        box.x + (column - (columns - 1) / 2) * stepX,
        zoneTop(node) + 0.5,
        box.z + (row - (rows - 1) / 2) * stepZ]});
    });
  }
  for (const person of crowd) {
    if (!person.target || !shown(person)) continue;
    const from = nodes.get(person.node);
    const to = nodes.get(person.target);
    if (!from || !to) continue;
    const ratio = clamp01(person.ratio || 0);
    const a = zoneAnchor(from);
    const b = zoneAnchor(to);
    const dx = b[0] - a[0];
    const dz = b[2] - a[2];
    const length = Math.hypot(dx, dz) || 1;
    const side = ((hashOf(String(person.id ?? '')) % 5) - 2) * 0.22;
    const height = zoneTop(from) + (zoneTop(to) - zoneTop(from)) * ratio + 0.5;
    placed.push({person, floor: ratio > 0.5 ? to.floor : from.floor, position: [
      a[0] + dx * ratio - (dz / length) * side,
      height,
      a[2] + dz * ratio + (dx / length) * side]});
  }
  return placed;
}

/**
 * Builds the list of things to draw.
 *
 * state: {path: string[], blocked: Set, hazards: Map(zoneId -> zone), origin: string|null,
 *         person: {id, node, target, ratio, historical}|null,   // the selected resident
 *         crowd: [{id, node, target, ratio, status}]}            // every resident (responders only)
 * options: {mode: '3d'|'2d', floor: number}
 *
 * In 3D every floor is drawn and floors above the selected one are see-through. In 2D only the
 * selected floor (plus the exits on floor 1) is drawn.
 */
export function describeScene(building, state, options) {
  const scene = {boxes: [], segments: [], labels: []};
  if (!building) return scene;
  const nodes = new Map(building.nodes.map(node => [node.id, node]));
  const selectedFloor = options.floor;
  const fullState = {...state, routeNodes: new Set(state.path || [])};
  const visible = node => options.mode === '3d' || node.floor === selectedFloor;
  const ghost = node => options.mode === '3d' && node.floor > selectedFloor;

  // Everyone to draw: the crowd plus the selected resident (who may not be in the crowd list).
  const crowd = (state.crowd || []).map(person => ({...person, selected: person.id === state.person?.id}));
  if (state.person && !crowd.some(person => person.selected)) crowd.push({status: 'MOVING', ...state.person, selected: true});
  const placed = crowdPositions(nodes, crowd);
  const insideByFloor = new Map();
  for (const item of placed) {
    if (item.person.status !== 'EVACUATED') insideByFloor.set(item.floor, (insideByFloor.get(item.floor) || 0) + 1);
  }
  const leftBy = new Map();
  for (const person of state.crowd || []) {
    if (person.status === 'EVACUATED') leftBy.set(person.node, (leftBy.get(person.node) || 0) + 1);
  }
  const hasCrowd = (state.crowd || []).length > 0;

  // Floor 11 is the roof zone itself, so only floors 1–10 get a floor slab.
  const floors = options.mode === '3d' ? [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] : [selectedFloor];
  for (const floor of floors) {
    if (floor > 10) continue;
    const seeThrough = options.mode === '3d' && floor > selectedFloor;
    scene.boxes.push(seeThrough
      ? {box: floorSlab(floor), color: COLORS.slab, alpha: GHOST.alpha, outline: true, outlineAlpha: GHOST.outlineAlpha}
      : {box: floorSlab(floor), color: COLORS.slab, alpha: 1, outline: true});
    if (options.mode === '3d') {
      const count = insideByFloor.get(floor);
      scene.labels.push({text: floorName(floor) + (hasCrowd && count ? t(` · ${count}명`,` · ${count} remaining`) : ''),
        position: [-FOOTPRINT.width / 2 - 2.6, floorBase(floor) + 1.2, 0],
        kind: floor === selectedFloor ? 'floor current' : 'floor'});
    }
  }

  for (const node of building.nodes) {
    if (!visible(node)) continue;
    const box = zoneBox(node);
    if (!box) continue;
    const look = zoneLook(node, fullState);
    const drawn = look.heightScale === 1 ? box
      : {...box, height: box.height * look.heightScale, y: box.y - box.height * (1 - look.heightScale) / 2};
    const seeThrough = ghost(node);
    scene.boxes.push(seeThrough
      ? {id: node.id, box: drawn, color: look.color, alpha: GHOST.alpha, outline: true, outlineAlpha: GHOST.outlineAlpha, pickable: false}
      : {id: node.id, box: drawn, color: look.color, alpha: 1, outline: true, pickable: true});
    const labelled = options.mode === '2d' || node.floor === selectedFloor || node.kind === 'exit';
    if (labelled && !seeThrough) {
      // Seen from straight above the origin pin hides the room name, so the 2D plan merges them.
      const isOrigin = options.mode === '2d' && node.id === state.origin;
      let text = shortName(node);
      if (isOrigin) text += t(' · 기준 위치',' · Origin');
      if (node.kind === 'exit' && hasCrowd) text += t(` · ${leftBy.get(node.id) || 0}명 대피`,` · ${leftBy.get(node.id) || 0} evacuated`);
      scene.labels.push({text,
        position: [drawn.x, drawn.y + drawn.height / 2 + 0.25, drawn.z],
        kind: isOrigin ? 'origin' : node.kind === 'exit' ? 'exit' : `zone ${look.condition}`});
    }
  }

  const path = state.path || [];
  for (let i = 1; i < path.length; i += 1) {
    const from = nodes.get(path[i - 1]);
    const to = nodes.get(path[i]);
    if (!from || !to || !visible(from) || !visible(to)) continue;
    scene.segments.push({from: zoneAnchor(from), to: zoneAnchor(to), color: COLORS.routeLine,
      alpha: ghost(from) && ghost(to) ? 0.35 : 1});
  }

  const origin = state.origin && nodes.get(state.origin);
  if (origin && visible(origin) && !ghost(origin)) {
    const box = zoneBox(origin);
    const top = box.y + box.height / 2;
    scene.boxes.push({box: {x: box.x, y: top + 1.0, z: box.z, width: 0.35, height: 2.0, depth: 0.35}, color: COLORS.origin, alpha: 1, outline: false});
    scene.boxes.push({box: {x: box.x, y: top + 2.2, z: box.z, width: 1.1, height: 0.7, depth: 1.1}, color: COLORS.origin, alpha: 1, outline: true});
    if (options.mode === '3d') scene.labels.push({text: t('기준 위치','Origin'), position: [box.x, top + 3.0, box.z], kind: 'origin'});
  }

  for (const {person, floor, position} of placed) {
    const onScreen = options.mode === '3d' ? floor <= selectedFloor : floor === selectedFloor;
    if (!onScreen) continue;
    const [x, y, z] = position;
    if (person.selected) {
      const historical = state.person?.historical;
      scene.boxes.push({box: {x, y: y + 0.4, z, width: 0.95, height: 1.9, depth: 0.95},
        color: historical ? COLORS.historical : COLORS.person, alpha: 1, outline: true});
      scene.labels.push({text: historical ? t('저장 당시 위치','Recorded position') : t('선택한 주민','Selected resident'), position: [x, y + 1.6, z],
        kind: historical ? 'person historical' : 'person'});
    } else {
      const look = RESIDENT_STATES[person.status] || RESIDENT_STATES.MOVING;
      // xray: residents on lower floors stay faintly visible through the floors above them.
      scene.boxes.push({box: {x, y, z, width: PERSON_SIZE.width, height: PERSON_SIZE.height, depth: PERSON_SIZE.width},
        color: hexToRgb(look.color), alpha: 1, outline: false, xray: options.mode === '3d' && floor < selectedFloor});
    }
  }
  return scene;
}

// ---------------------------------------------------------------------------------------------
// Small column-major 4x4 matrix helpers
// ---------------------------------------------------------------------------------------------

export const mat4 = {
  multiply(a, b) {
    const out = new Float32Array(16);
    for (let col = 0; col < 4; col += 1) {
      for (let row = 0; row < 4; row += 1) {
        let sum = 0;
        for (let k = 0; k < 4; k += 1) sum += a[k * 4 + row] * b[col * 4 + k];
        out[col * 4 + row] = sum;
      }
    }
    return out;
  },
  perspective(fovY, aspect, near, far) {
    const f = 1 / Math.tan(fovY / 2);
    const out = new Float32Array(16);
    out[0] = f / aspect; out[5] = f; out[10] = (far + near) / (near - far); out[11] = -1; out[14] = (2 * far * near) / (near - far);
    return out;
  },
  orthographic(left, right, bottom, top, near, far) {
    const out = new Float32Array(16);
    out[0] = 2 / (right - left); out[5] = 2 / (top - bottom); out[10] = -2 / (far - near);
    out[12] = -(right + left) / (right - left); out[13] = -(top + bottom) / (top - bottom); out[14] = -(far + near) / (far - near); out[15] = 1;
    return out;
  },
  lookAt(eye, target, up) {
    const sub = (a, b) => a.map((v, i) => v - b[i]);
    const norm = v => { const l = Math.hypot(...v) || 1; return v.map(x => x / l); };
    const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const z = norm(sub(eye, target));
    const x = norm(cross(up, z));
    const y = cross(z, x);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, -dot(x, eye), -dot(y, eye), -dot(z, eye), 1]);
  },
  /** Places a unit cube (centred at the origin) as the given box. */
  box({x, y, z, width, height, depth}) {
    return new Float32Array([width, 0, 0, 0, 0, height, 0, 0, 0, 0, depth, 0, x, y, z, 1]);
  },
  /** Places a unit cube as a thin bar from `from` to `to`. */
  segment(from, to, thickness) {
    const d = to.map((v, i) => v - from[i]);
    const length = Math.hypot(...d) || 1e-6;
    const ax = d.map(v => v / length);
    const helper = Math.abs(ax[1]) > 0.9 ? [1, 0, 0] : [0, 1, 0];
    let bx = [ax[1] * helper[2] - ax[2] * helper[1], ax[2] * helper[0] - ax[0] * helper[2], ax[0] * helper[1] - ax[1] * helper[0]];
    const bl = Math.hypot(...bx);
    bx = bx.map(v => v / bl);
    const cx = [ax[1] * bx[2] - ax[2] * bx[1], ax[2] * bx[0] - ax[0] * bx[2], ax[0] * bx[1] - ax[1] * bx[0]];
    const mid = from.map((v, i) => (v + to[i]) / 2);
    return new Float32Array([
      ax[0] * length, ax[1] * length, ax[2] * length, 0,
      bx[0] * thickness, bx[1] * thickness, bx[2] * thickness, 0,
      cx[0] * thickness, cx[1] * thickness, cx[2] * thickness, 0,
      mid[0], mid[1], mid[2], 1]);
  },
  invert(m) {
    const inv = new Float32Array(16);
    inv[0] = m[5] * m[10] * m[15] - m[5] * m[11] * m[14] - m[9] * m[6] * m[15] + m[9] * m[7] * m[14] + m[13] * m[6] * m[11] - m[13] * m[7] * m[10];
    inv[4] = -m[4] * m[10] * m[15] + m[4] * m[11] * m[14] + m[8] * m[6] * m[15] - m[8] * m[7] * m[14] - m[12] * m[6] * m[11] + m[12] * m[7] * m[10];
    inv[8] = m[4] * m[9] * m[15] - m[4] * m[11] * m[13] - m[8] * m[5] * m[15] + m[8] * m[7] * m[13] + m[12] * m[5] * m[11] - m[12] * m[7] * m[9];
    inv[12] = -m[4] * m[9] * m[14] + m[4] * m[10] * m[13] + m[8] * m[5] * m[14] - m[8] * m[6] * m[13] - m[12] * m[5] * m[10] + m[12] * m[6] * m[9];
    inv[1] = -m[1] * m[10] * m[15] + m[1] * m[11] * m[14] + m[9] * m[2] * m[15] - m[9] * m[3] * m[14] - m[13] * m[2] * m[11] + m[13] * m[3] * m[10];
    inv[5] = m[0] * m[10] * m[15] - m[0] * m[11] * m[14] - m[8] * m[2] * m[15] + m[8] * m[3] * m[14] + m[12] * m[2] * m[11] - m[12] * m[3] * m[10];
    inv[9] = -m[0] * m[9] * m[15] + m[0] * m[11] * m[13] + m[8] * m[1] * m[15] - m[8] * m[3] * m[13] - m[12] * m[1] * m[11] + m[12] * m[3] * m[9];
    inv[13] = m[0] * m[9] * m[14] - m[0] * m[10] * m[13] - m[8] * m[1] * m[14] + m[8] * m[2] * m[13] + m[12] * m[1] * m[10] - m[12] * m[2] * m[9];
    inv[2] = m[1] * m[6] * m[15] - m[1] * m[7] * m[14] - m[5] * m[2] * m[15] + m[5] * m[3] * m[14] + m[13] * m[2] * m[7] - m[13] * m[3] * m[6];
    inv[6] = -m[0] * m[6] * m[15] + m[0] * m[7] * m[14] + m[4] * m[2] * m[15] - m[4] * m[3] * m[14] - m[12] * m[2] * m[7] + m[12] * m[3] * m[6];
    inv[10] = m[0] * m[5] * m[15] - m[0] * m[7] * m[13] - m[4] * m[1] * m[15] + m[4] * m[3] * m[13] + m[12] * m[1] * m[7] - m[12] * m[3] * m[5];
    inv[14] = -m[0] * m[5] * m[14] + m[0] * m[6] * m[13] + m[4] * m[1] * m[14] - m[4] * m[2] * m[13] - m[12] * m[1] * m[6] + m[12] * m[2] * m[5];
    inv[3] = -m[1] * m[6] * m[11] + m[1] * m[7] * m[10] + m[5] * m[2] * m[11] - m[5] * m[3] * m[10] - m[9] * m[2] * m[7] + m[9] * m[3] * m[6];
    inv[7] = m[0] * m[6] * m[11] - m[0] * m[7] * m[10] - m[4] * m[2] * m[11] + m[4] * m[3] * m[10] + m[8] * m[2] * m[7] - m[8] * m[3] * m[6];
    inv[11] = -m[0] * m[5] * m[11] + m[0] * m[7] * m[9] + m[4] * m[1] * m[11] - m[4] * m[3] * m[9] - m[8] * m[1] * m[7] + m[8] * m[3] * m[5];
    inv[15] = m[0] * m[5] * m[10] - m[0] * m[6] * m[9] - m[4] * m[1] * m[10] + m[4] * m[2] * m[9] + m[8] * m[1] * m[6] - m[8] * m[2] * m[5];
    const det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12];
    if (!det) return null;
    return inv.map(v => v / det);
  },
  transform(m, [x, y, z, w]) {
    return [0, 1, 2, 3].map(row => m[row] * x + m[4 + row] * y + m[8 + row] * z + m[12 + row] * w);
  },
};

// ---------------------------------------------------------------------------------------------
// Cameras and picking (pure)
// ---------------------------------------------------------------------------------------------

export const DEFAULT_ORBIT = {yaw: -0.55, pitch: 0.62, zoom: 1};
export const DEFAULT_PLAN = {x: 0, z: 0.6, zoom: 1};
const ORBIT_DISTANCE = 72;
const BUILDING_MID_HEIGHT = 5 * FLOOR_HEIGHT;
const PLAN_EXTENT = {width: 48, depth: 24};

/** View-projection matrix and eye position for the current mode. */
export function cameraFor(mode, floor, aspect, orbit = DEFAULT_ORBIT, plan = DEFAULT_PLAN) {
  if (mode === '2d') {
    const scale = Math.max(PLAN_EXTENT.width / aspect, PLAN_EXTENT.depth) * plan.zoom;
    const halfHeight = scale / 2;
    const halfWidth = halfHeight * aspect;
    const top = floorBase(floor) + 40;
    const eye = [plan.x, top, plan.z];
    const view = mat4.lookAt(eye, [plan.x, top - 1, plan.z], [0, 0, -1]);
    const projection = mat4.orthographic(-halfWidth, halfWidth, -halfHeight, halfHeight, 0.1, 80);
    return {viewProjection: mat4.multiply(projection, view), eye, worldPerPixelHeight: 2 * halfHeight};
  }
  // Aim halfway between the selected floor and the middle of the building so both stay in view.
  const target = [0, (floorBase(Math.min(floor, 10)) + 1.2 + BUILDING_MID_HEIGHT) / 2, 0];
  const distance = ORBIT_DISTANCE * orbit.zoom;
  const eye = [
    target[0] + distance * Math.cos(orbit.pitch) * Math.sin(orbit.yaw),
    target[1] + distance * Math.sin(orbit.pitch),
    target[2] + distance * Math.cos(orbit.pitch) * Math.cos(orbit.yaw),
  ];
  const view = mat4.lookAt(eye, target, [0, 1, 0]);
  const projection = mat4.perspective(Math.PI * 40 / 180, aspect, 0.5, 400);
  return {viewProjection: mat4.multiply(projection, view), eye, worldPerPixelHeight: null};
}

/** Projects a world point to CSS pixels; null when it is behind the camera. */
export function projectPoint(viewProjection, point, width, height) {
  const [x, y, z, w] = mat4.transform(viewProjection, [...point, 1]);
  if (w <= 0) return null;
  const nx = x / w;
  const ny = y / w;
  const nz = z / w;
  if (nz < -1 || nz > 1) return null;
  return {x: (nx + 1) / 2 * width, y: (1 - ny) / 2 * height};
}

/** Returns the id of the nearest pickable box under normalised device coordinates (nx, ny). */
export function pickBox(scene, viewProjection, nx, ny) {
  const inverse = mat4.invert(viewProjection);
  if (!inverse) return null;
  const unproject = z => { const p = mat4.transform(inverse, [nx, ny, z, 1]); return p.slice(0, 3).map(v => v / p[3]); };
  const origin = unproject(-1);
  const far = unproject(1);
  const direction = far.map((v, i) => v - origin[i]);
  let best = null;
  for (const item of scene.boxes) {
    if (!item.pickable) continue;
    const {x, y, z, width, height, depth} = item.box;
    const min = [x - width / 2, y - height / 2, z - depth / 2];
    const max = [x + width / 2, y + height / 2, z + depth / 2];
    let near = -Infinity;
    let farHit = Infinity;
    let missed = false;
    for (let axis = 0; axis < 3 && !missed; axis += 1) {
      if (Math.abs(direction[axis]) < 1e-9) {
        if (origin[axis] < min[axis] || origin[axis] > max[axis]) missed = true;
        continue;
      }
      let t1 = (min[axis] - origin[axis]) / direction[axis];
      let t2 = (max[axis] - origin[axis]) / direction[axis];
      if (t1 > t2) [t1, t2] = [t2, t1];
      near = Math.max(near, t1);
      farHit = Math.min(farHit, t2);
      if (near > farHit) missed = true;
    }
    if (!missed && farHit >= 0 && (!best || near < best.t)) best = {id: item.id, t: near};
  }
  return best ? best.id : null;
}

// ---------------------------------------------------------------------------------------------
// WebGL renderer
// ---------------------------------------------------------------------------------------------

const VERTEX_SHADER = `
attribute vec3 a_position;
attribute vec3 a_normal;
uniform mat4 u_viewProjection;
uniform mat4 u_model;
varying vec3 v_normal;
void main() {
  v_normal = (u_model * vec4(a_normal, 0.0)).xyz;
  gl_Position = u_viewProjection * u_model * vec4(a_position, 1.0);
}`;

const FRAGMENT_SHADER = `
precision mediump float;
varying vec3 v_normal;
uniform vec4 u_color;
uniform float u_lighting;
void main() {
  float light = 1.0;
  if (u_lighting > 0.5) {
    vec3 n = normalize(v_normal);
    light = 0.64 + 0.36 * max(dot(n, normalize(vec3(0.45, 0.85, 0.35))), 0.0)
          + 0.08 * max(dot(n, normalize(vec3(-0.6, 0.2, -0.4))), 0.0);
  }
  gl_FragColor = vec4(min(u_color.rgb * light, vec3(1.0)), u_color.a);
}`;

/** Unit cube centred at the origin: 36 triangle vertices and 24 outline vertices. */
function cubeGeometry() {
  const faces = [
    [[1, 0, 0], [[0.5, -0.5, -0.5], [0.5, 0.5, -0.5], [0.5, 0.5, 0.5], [0.5, -0.5, 0.5]]],
    [[-1, 0, 0], [[-0.5, -0.5, 0.5], [-0.5, 0.5, 0.5], [-0.5, 0.5, -0.5], [-0.5, -0.5, -0.5]]],
    [[0, 1, 0], [[-0.5, 0.5, -0.5], [-0.5, 0.5, 0.5], [0.5, 0.5, 0.5], [0.5, 0.5, -0.5]]],
    [[0, -1, 0], [[-0.5, -0.5, 0.5], [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [0.5, -0.5, 0.5]]],
    [[0, 0, 1], [[-0.5, -0.5, 0.5], [0.5, -0.5, 0.5], [0.5, 0.5, 0.5], [-0.5, 0.5, 0.5]]],
    [[0, 0, -1], [[0.5, -0.5, -0.5], [-0.5, -0.5, -0.5], [-0.5, 0.5, -0.5], [0.5, 0.5, -0.5]]],
  ];
  const triangles = [];
  for (const [normal, [a, b, c, d]] of faces) {
    for (const corner of [a, b, c, a, c, d]) triangles.push(...corner, ...normal);
  }
  const corners = [];
  for (const x of [-0.5, 0.5]) for (const y of [-0.5, 0.5]) for (const z of [-0.5, 0.5]) corners.push([x, y, z]);
  const lines = [];
  for (let i = 0; i < 8; i += 1) {
    for (let j = i + 1; j < 8; j += 1) {
      const differing = corners[i].filter((v, axis) => v !== corners[j][axis]).length;
      if (differing === 1) lines.push(...corners[i], 0, 0, 0, ...corners[j], 0, 0, 0);
    }
  }
  return {triangles: new Float32Array(triangles), lines: new Float32Array(lines)};
}

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error('WebGL shader failed: ' + gl.getShaderInfoLog(shader));
  return shader;
}

/**
 * Draws the building on a <canvas> and keeps HTML labels positioned over it.
 * Throws from the constructor when WebGL is unavailable, so callers can fall back to the SVG schematic.
 */
export class BuildingView {
  constructor(canvas, labelLayer, {onPick = () => {}, onLost = () => {}} = {}) {
    const gl = canvas.getContext('webgl', {antialias: true, alpha: false, preserveDrawingBuffer: false});
    if (!gl) throw new Error('WebGL is not available');
    this.canvas = canvas;
    this.labelLayer = labelLayer;
    this.gl = gl;
    this.onPick = onPick;
    this.building = null;
    this.state = {path: [], blocked: new Set(), hazards: new Map(), origin: null, person: null};
    this.mode = '3d';
    this.floor = 7;
    this.orbit = {...DEFAULT_ORBIT};
    this.plan = {...DEFAULT_PLAN};
    this.scene = describeScene(null, this.state, {mode: this.mode, floor: this.floor});
    this.camera = null;
    this.labels = [];
    this.frameRequested = false;
    this.lost = false;
    this.setupGl();
    this.bindInput();
    canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); this.lost = true; onLost(); });
    if (typeof ResizeObserver === 'function') new ResizeObserver(() => this.requestRender()).observe(canvas);
    else window.addEventListener('resize', () => this.requestRender());
  }

  setupGl() {
    const gl = this.gl;
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error('WebGL program failed: ' + gl.getProgramInfoLog(program));
    this.program = program;
    this.locations = {
      position: gl.getAttribLocation(program, 'a_position'), normal: gl.getAttribLocation(program, 'a_normal'),
      viewProjection: gl.getUniformLocation(program, 'u_viewProjection'), model: gl.getUniformLocation(program, 'u_model'),
      color: gl.getUniformLocation(program, 'u_color'), lighting: gl.getUniformLocation(program, 'u_lighting'),
    };
    const geometry = cubeGeometry();
    this.buffers = {triangles: this.upload(geometry.triangles), lines: this.upload(geometry.lines)};
    this.counts = {triangles: geometry.triangles.length / 6, lines: geometry.lines.length / 6};
  }

  upload(data) {
    const gl = this.gl;
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
    return buffer;
  }

  // ---- public API --------------------------------------------------------------------------

  setBuilding(building) { this.building = building; this.requestRender(); }

  setMode(mode) { this.mode = mode === '2d' ? '2d' : '3d'; this.requestRender(); }

  /** state: see describeScene. floor: the floor selected in the dashboard. */
  update(state, floor) { this.state = state; this.floor = floor; this.requestRender(); }

  resetCamera() { this.orbit = {...DEFAULT_ORBIT}; this.plan = {...DEFAULT_PLAN}; this.requestRender(); }

  requestRender() {
    if (this.frameRequested || this.lost) return;
    this.frameRequested = true;
    requestAnimationFrame(() => { this.frameRequested = false; this.render(); });
  }

  // ---- drawing -----------------------------------------------------------------------------

  render() {
    const {gl, canvas} = this;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height || this.lost) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const pixelWidth = Math.round(width * ratio);
    const pixelHeight = Math.round(height * ratio);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) { canvas.width = pixelWidth; canvas.height = pixelHeight; }

    this.scene = describeScene(this.building, this.state, {mode: this.mode, floor: this.floor});
    this.camera = cameraFor(this.mode, this.floor, width / height, this.orbit, this.plan);

    gl.viewport(0, 0, pixelWidth, pixelHeight);
    gl.clearColor(0.965, 0.976, 0.984, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(this.program);
    gl.uniformMatrix4fv(this.locations.viewProjection, false, this.camera.viewProjection);

    const opaque = this.scene.boxes.filter(item => item.alpha >= 1);
    const seeThrough = this.scene.boxes.filter(item => item.alpha < 1);
    const distance = item => Math.hypot(item.box.x - this.camera.eye[0], item.box.y - this.camera.eye[1], item.box.z - this.camera.eye[2]);
    seeThrough.sort((a, b) => distance(b) - distance(a));

    // Solid zones are pushed slightly back so their outlines stay crisp on top.
    gl.enable(gl.POLYGON_OFFSET_FILL);
    gl.polygonOffset(1, 1);
    gl.depthMask(true);
    for (const item of opaque) this.drawCube(mat4.box(item.box), item.color, 1, true);
    for (const segment of this.scene.segments) this.drawCube(mat4.segment(segment.from, segment.to, 0.45), segment.color, segment.alpha, true);
    gl.disable(gl.POLYGON_OFFSET_FILL);
    for (const item of opaque) if (item.outline) this.drawOutline(mat4.box(item.box), item.outlineAlpha ?? 0.55);

    gl.depthMask(false);
    for (const item of seeThrough) {
      this.drawCube(mat4.box(item.box), item.color, item.alpha, true);
      if (item.outline) this.drawOutline(mat4.box(item.box), item.outlineAlpha ?? item.alpha);
    }
    if (this.mode === '3d') {
      // X-ray pass: route parts and lower-floor residents hidden behind floors stay faintly visible.
      gl.disable(gl.DEPTH_TEST);
      for (const segment of this.scene.segments) this.drawCube(mat4.segment(segment.from, segment.to, 0.3), segment.color, 0.3, false);
      for (const item of opaque) if (item.xray) this.drawCube(mat4.box(item.box), item.color, 0.4, false);
      gl.enable(gl.DEPTH_TEST);
    }
    gl.depthMask(true);
    this.placeLabels(width, height);
  }

  bindGeometry(buffer) {
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.enableVertexAttribArray(this.locations.position);
    gl.vertexAttribPointer(this.locations.position, 3, gl.FLOAT, false, 24, 0);
    gl.enableVertexAttribArray(this.locations.normal);
    gl.vertexAttribPointer(this.locations.normal, 3, gl.FLOAT, false, 24, 12);
  }

  drawCube(model, color, alpha, lit) {
    const gl = this.gl;
    this.bindGeometry(this.buffers.triangles);
    gl.uniformMatrix4fv(this.locations.model, false, model);
    gl.uniform4f(this.locations.color, color[0], color[1], color[2], alpha);
    gl.uniform1f(this.locations.lighting, lit ? 1 : 0);
    gl.drawArrays(gl.TRIANGLES, 0, this.counts.triangles);
  }

  drawOutline(model, alpha) {
    const gl = this.gl;
    this.bindGeometry(this.buffers.lines);
    gl.uniformMatrix4fv(this.locations.model, false, model);
    gl.uniform4f(this.locations.color, COLORS.outline[0], COLORS.outline[1], COLORS.outline[2], Math.min(1, alpha));
    gl.uniform1f(this.locations.lighting, 0);
    gl.drawArrays(gl.LINES, 0, this.counts.lines);
  }

  placeLabels(width, height) {
    const items = this.scene.labels;
    while (this.labels.length < items.length) {
      const element = document.createElement('span');
      this.labelLayer.append(element);
      this.labels.push(element);
    }
    this.labels.forEach((element, index) => {
      const item = items[index];
      const point = item && projectPoint(this.camera.viewProjection, item.position, width, height);
      if (!point || point.x < -40 || point.y < -20 || point.x > width + 40 || point.y > height + 20) { element.hidden = true; return; }
      element.hidden = false;
      element.textContent = item.text;
      element.className = 'scene-label ' + item.kind;
      element.style.transform = `translate(${point.x.toFixed(1)}px, ${point.y.toFixed(1)}px) translate(-50%, -100%)`;
    });
  }

  // ---- input: drag to rotate (3D) or pan (2D), wheel/keys to zoom, click to inspect ----------

  bindInput() {
    const canvas = this.canvas;
    let drag = null;
    canvas.addEventListener('pointerdown', event => {
      drag = {x: event.clientX, y: event.clientY, moved: 0};
      try { canvas.setPointerCapture(event.pointerId); } catch { /* capture is optional */ }
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      drag = {x: event.clientX, y: event.clientY, moved: drag.moved + Math.abs(dx) + Math.abs(dy)};
      this.moveCamera(dx, dy);
    });
    const finish = event => {
      if (drag && drag.moved < 5 && event.type === 'pointerup') this.pickAt(event.clientX, event.clientY);
      drag = null;
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
    canvas.addEventListener('wheel', event => { event.preventDefault(); this.zoomBy(Math.exp(event.deltaY * 0.0012)); }, {passive: false});
    canvas.addEventListener('keydown', event => {
      // Keys move the camera (the opposite of dragging, which moves the picture).
      const step = 24;
      const actions = {
        ArrowLeft: () => this.moveCamera(step, 0), ArrowRight: () => this.moveCamera(-step, 0),
        ArrowUp: () => this.moveCamera(0, step), ArrowDown: () => this.moveCamera(0, -step),
        '+': () => this.zoomBy(0.85), '=': () => this.zoomBy(0.85), '-': () => this.zoomBy(1.18), '0': () => this.resetCamera(),
      };
      if (!actions[event.key]) return;
      event.preventDefault();
      actions[event.key]();
    });
  }

  moveCamera(dx, dy) {
    if (this.mode === '3d') {
      this.orbit.yaw -= dx * 0.008;
      this.orbit.pitch = Math.min(1.5, Math.max(0.12, this.orbit.pitch + dy * 0.006));
    } else {
      const perPixel = (this.camera?.worldPerPixelHeight || PLAN_EXTENT.depth) / (this.canvas.clientHeight || 1);
      this.plan.x -= dx * perPixel;
      this.plan.z -= dy * perPixel;
    }
    this.requestRender();
  }

  zoomBy(factor) {
    const target = this.mode === '3d' ? this.orbit : this.plan;
    target.zoom = Math.min(this.mode === '3d' ? 2.2 : 1.6, Math.max(this.mode === '3d' ? 0.35 : 0.25, target.zoom * factor));
    this.requestRender();
  }

  pickAt(clientX, clientY) {
    if (!this.camera || !this.building) return;
    const rect = this.canvas.getBoundingClientRect();
    const nx = (clientX - rect.left) / rect.width * 2 - 1;
    const ny = 1 - (clientY - rect.top) / rect.height * 2;
    const id = pickBox(this.scene, this.camera.viewProjection, nx, ny);
    const node = id && this.building.nodes.find(n => n.id === id);
    this.onPick(node ? {node, text: describeZone(node, this.state)} : null);
  }
}

