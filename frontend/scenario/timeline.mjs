/**
 * Evacuation timeline for the responder dashboard.
 *
 * The live API only returns the current frame, so the browser records every new live responder
 * frame (fire, smoke, blocked zones, route, all residents) and lets the responder play it back,
 * scrub, step and jump to events — in the spirit of fire_evac/replay.js.
 *
 * Recordings live in this tab's memory only (never localStorage, never the CSE) and are cleared on
 * logout, reset or a new incident. Playback never replaces the live guidance cards; the map shows a
 * "기록 재생" banner while it is not live.
 *
 * FrameRecorder, TimelinePlayer and frameEvents are DOM-free and unit-tested in Node.
 */
import {RESIDENT_STATES} from './building-view.mjs';
import './locale.js';
const {t,getLanguage} = globalThis.FireRouteLocale;

const STATUS_ORDER = ['EVACUATED', 'MOVING', 'QUEUED', 'WAITING', 'NO_ROUTE', 'BLOCKED_IN_TRANSIT'];
const STATUS_CODE = new Map(STATUS_ORDER.map((status, index) => [status, index]));
const MAX_FRAMES = 2400;
/** Frames further apart than this are not interpolated (e.g. after "+30초"): people snap instead of gliding. */
const MAX_INTERPOLATION_GAP = 3;
/**
 * Congestion-aware routing can flip the fixed-origin exit back and forth every few seconds.
 * Route-change events closer together than this are not listed (the map still shows every frame).
 */
const ROUTE_EVENT_QUIET_SECONDS = 20;

export const EVENT_KINDS = {
  start: {label: '기록 시작', color: '#5b6b82'},
  route: {label: '경로', color: '#7a4fd6'},
  noroute: {label: '경로 없음', color: '#d64545'},
  blocked: {label: '차단', color: '#c43b41'},
  collapse: {label: '붕괴', color: '#6e1a1d'},
  fire: {label: '화재 확산', color: '#e8742a'},
  device: {label: '표시 장치', color: '#b7791f'},
  evac: {label: '대피', color: '#1f9d6b'},
  stuck: {label: '고립', color: '#9b1f2a'},
};

export function clock(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds) || 0));
  return String(Math.floor(value / 60)).padStart(2, '0') + ':' + String(value % 60).padStart(2, '0');
}

const floorOf = id => { const match = /^F(\d+)-/.exec(id); return match ? Number(match[1]) : 1; };
const floorName = (floor, english) => floor === 11 ? (english ? 'Roof' : '옥상') : (english ? `Floor ${floor}` : `${floor}층`);
const listNames = (ids, english) => ids.slice(0, 3).join(', ') + (ids.length > 3 ? (english ? ` and ${ids.length - 3} more` : ` 외 ${ids.length - 3}곳`) : '');
const sameList = (a, b) => a.length === b.length && a.every((value, index) => value === b[index]);

// ---------------------------------------------------------------------------------------------
// Events between two consecutive recorded frames
// ---------------------------------------------------------------------------------------------

/** What changed between two recorded frames, with text in both supported languages. */
export function frameEvents(previous, current, ids) {
  const at = current.second;
  const event = (kind, text, english, floor = null) => ({second: at, kind, text, english, floor});
  if (!previous) {
    const route = current.guidance === 'ROUTE_AVAILABLE' ? `경로 ${current.exit}` : '경로 없음';
    const englishRoute = current.guidance === 'ROUTE_AVAILABLE' ? `Route to ${current.exit}` : 'No route';
    return [event('start', `기록 시작 · ${route} · 대피 완료 ${current.counts.EVACUATED}/${current.total}명`,
      `Recording started · ${englishRoute} · ${current.counts.EVACUATED}/${current.total} evacuated`)];
  }
  const events = [];

  if (previous.guidance !== current.guidance) {
    if (current.guidance === 'NO_VERIFIED_ROUTE') events.push(event('noroute', '고정 출발점에서 확인된 경로 없음 · 방향 안내를 지움', 'No verified route from the fixed origin · guidance cleared'));
    else if (current.guidance === 'ROUTE_AVAILABLE') events.push(event('route', `경로 다시 확인 · ${current.exit}`, `Route restored · ${current.exit}`));
  } else if (current.guidance === 'ROUTE_AVAILABLE') {
    if (previous.exit !== current.exit) events.push(event('route', `출구 변경 ${previous.exit} → ${current.exit}`, `Exit changed ${previous.exit} → ${current.exit}`));
    else if (!sameList(previous.path, current.path)) events.push(event('route', `우회 경로로 변경 · 같은 출구 ${current.exit}`, `Alternate route to ${current.exit}`));
  }

  const wasBlocked = new Set(previous.blocked);
  const newlyBlocked = [...current.blocked].filter(index => !wasBlocked.has(index)).map(index => ids[index]);
  if (newlyBlocked.length) events.push(event('blocked', `차단 추가: ${listNames(newlyBlocked)}`, `New blockages · ${listNames(newlyBlocked,true)}`, floorOf(newlyBlocked[0])));

  const collapsed = [];
  for (let i = 0; i < ids.length; i += 1) if (current.collapsed[i] && !previous.collapsed[i]) collapsed.push(ids[i]);
  if (collapsed.length) events.push(event('collapse', `붕괴: ${listNames(collapsed)}`, `Collapsed zones · ${listNames(collapsed,true)}`, floorOf(collapsed[0])));

  const fireFloors = frame => { const floors = new Set(); frame.fire.forEach((value, i) => { if (value > 0) floors.add(floorOf(ids[i])); }); return floors; };
  const before = fireFloors(previous);
  const reached = [...fireFloors(current)].filter(floor => !before.has(floor)).sort((a, b) => a - b);
  if (reached.length) {
    const koreanFloors = reached.map(floor => floorName(floor,false)).join(', ');
    const englishFloors = reached.map(floor => floorName(floor,true)).join(', ');
    events.push(before.size ? event('fire', `${koreanFloors}으로 화재 확산`, `Fire spread to ${englishFloors}`, reached[0])
      : event('fire', `${koreanFloors}에서 화재 감지`, `Fire detected on ${englishFloors}`, reached[0]));
  }

  if (Number.isInteger(current.ack) && Number.isInteger(previous.ack)) {
    if (current.ack < 3 && previous.ack === 3) events.push(event('device', `표시 장치 응답 ${current.ack}/3 · 전달 미완료(INCOMPLETE)`, `${current.ack}/3 sign ACKs · delivery incomplete`));
    if (current.ack === 3 && previous.ack < 3) events.push(event('device', '표시 장치 응답 3/3 회복', 'Sign ACKs restored to 3/3'));
  }

  const total = current.total || 1;
  const done = count => count / total;
  const was = previous.counts.EVACUATED;
  const now = current.counts.EVACUATED;
  if (was === 0 && now > 0) events.push(event('evac', `첫 대피 완료 (${now}명)`, `First evacuation (${now})`, 1));
  for (const mark of [0.25, 0.5, 0.75, 1]) {
    if (done(was) < mark && done(now) >= mark) events.push(event('evac', `대피 완료 ${Math.round(mark * 100)}% (${now}/${total}명)`, `${Math.round(mark * 100)}% evacuated (${now}/${total})`, 1));
  }

  const stuck = frame => frame.counts.NO_ROUTE + frame.counts.BLOCKED_IN_TRANSIT;
  if (stuck(previous) === 0 && stuck(current) > 0) events.push(event('stuck', `경로 없음·고립 주민 발생 (${stuck(current)}명)`, `Residents without a route or blocked in transit (${stuck(current)})`));
  return events;
}

// ---------------------------------------------------------------------------------------------
// Recorder: compact storage of live frames
// ---------------------------------------------------------------------------------------------

export class FrameRecorder {
  constructor(limit = MAX_FRAMES) {
    this.limit = limit;
    this.ids = null;
    this.frames = [];
    this.events = [];
  }

  /** Zone ids and link lengths come from /api/v1/building. Recording starts after this. */
  setBuilding(building) {
    this.ids = building.nodes.map(node => node.id);
    this.index = new Map(this.ids.map((id, i) => [id, i]));
    this.lengths = new Map();
    for (const edge of building.edges) {
      this.lengths.set(edge.from + '|' + edge.to, edge.length_m);
      this.lengths.set(edge.to + '|' + edge.from, edge.length_m);
    }
    this.clear();
  }

  clear() {
    this.frames = [];
    this.events = [];
    this.residentIds = null;
    this.lastRouteEvent = undefined;
  }

  get length() { return this.frames.length; }
  get firstSecond() { return this.frames.length ? this.frames[0].second : 0; }
  get lastSecond() { return this.frames.length ? this.frames[this.frames.length - 1].second : 0; }

  /**
   * Stores a live responder view if it is newer than the last recorded frame.
   * `path` is the route the map draws for that frame. Returns the new events, or null when skipped.
   */
  record(view, path) {
    if (!this.ids || !Number.isInteger(view?.simulation_second) || !Array.isArray(view.residents)) return null;
    const last = this.frames[this.frames.length - 1];
    if (last && view.simulation_second <= last.second) return null;

    const size = this.ids.length;
    const fire = new Uint8Array(size);
    const smoke = new Uint8Array(size);
    const collapsed = new Uint8Array(size);
    for (const zone of view.hazards?.zones || []) {
      const i = this.index.get(zone.zone_id);
      if (i === undefined) continue;
      fire[i] = Math.round(zone.fire_index);
      smoke[i] = Math.round(zone.smoke_index);
      collapsed[i] = zone.collapsed ? 1 : 0;
    }
    const blocked = Uint16Array.from((view.hazards?.blocked_nodes || []).map(id => this.index.get(id)).filter(i => i !== undefined));

    if (!this.residentIds) this.residentIds = view.residents.map(person => person.resident_id);
    const people = new Map(view.residents.map(person => [person.resident_id, person]));
    const count = this.residentIds.length;
    const node = new Int16Array(count).fill(-1);
    const target = new Int16Array(count).fill(-1);
    const ratio = new Float32Array(count);
    const status = new Uint8Array(count);
    const counts = Object.fromEntries(STATUS_ORDER.map(name => [name, 0]));
    this.residentIds.forEach((id, r) => {
      const person = people.get(id);
      if (!person) return;
      node[r] = this.index.get(person.node) ?? -1;
      target[r] = person.target ? (this.index.get(person.target) ?? -1) : -1;
      const length = person.target ? this.lengths.get(person.node + '|' + person.target) : 0;
      ratio[r] = length ? Math.min(1, person.progress_m / length) : 0;
      status[r] = STATUS_CODE.get(person.status) ?? STATUS_CODE.get('MOVING');
      counts[STATUS_ORDER[status[r]]] += 1;
    });

    const frame = {
      second: view.simulation_second, version: view.route_version, guidance: view.guidance_status,
      exit: view.route?.target_exit || null, path: [...(path || [])], ack: view.delivery?.ack_count ?? null,
      fire, smoke, collapsed, blocked, node, target, ratio, status, counts, total: count,
    };
    const events = frameEvents(last || null, frame, this.ids).filter(item => {
      if (item.kind !== 'route') return true;
      const quiet = this.lastRouteEvent === undefined || item.second - this.lastRouteEvent >= ROUTE_EVENT_QUIET_SECONDS;
      if (quiet) this.lastRouteEvent = item.second;
      return quiet;
    });
    this.frames.push(frame);
    this.events.push(...events);
    if (this.frames.length > this.limit) {
      this.frames.shift();
      const first = this.frames[0].second;
      this.events = this.events.filter(item => item.second >= first);
    }
    return events;
  }

  /** Index of the last frame at or before `second` (0 when before the first frame). */
  indexAt(second) {
    let low = 0;
    let high = this.frames.length - 1;
    while (low < high) {
      const middle = (low + high + 1) >> 1;
      if (this.frames[middle].second <= second) low = middle; else high = middle - 1;
    }
    return low;
  }

  /** Frame `i` in the same shape the map uses for live data. */
  decode(i) {
    const frame = this.frames[i];
    const hazards = new Map();
    this.ids.forEach((id, z) => {
      if (id.startsWith('EXIT')) return;
      hazards.set(id, {zone_id: id, fire_index: frame.fire[z], smoke_index: frame.smoke[z], collapsed: frame.collapsed[z] === 1});
    });
    const residents = this.residentIds.map((id, r) => ({
      id, node: this.ids[frame.node[r]], target: frame.target[r] >= 0 ? this.ids[frame.target[r]] : null,
      ratio: frame.ratio[r], status: STATUS_ORDER[frame.status[r]],
    }));
    return {
      second: frame.second, version: frame.version, guidance: frame.guidance, exit: frame.exit, path: frame.path,
      ack: frame.ack, blocked: new Set([...frame.blocked].map(z => this.ids[z])), hazards, residents,
      counts: frame.counts, total: frame.total,
    };
  }

  /**
   * The picture at a (possibly fractional) simulation second. Hazards and route step with frames;
   * residents glide between two close frames so movement looks continuous.
   */
  sample(second) {
    if (!this.frames.length) return null;
    const clamped = Math.min(this.lastSecond, Math.max(this.firstSecond, second));
    const i = this.indexAt(clamped);
    const result = this.decode(i);
    result.second = clamped;
    const a = this.frames[i];
    const b = this.frames[i + 1];
    if (!b || b.second - a.second > MAX_INTERPOLATION_GAP) return result;
    const t = (clamped - a.second) / (b.second - a.second);
    result.residents = result.residents.map((person, r) => {
      const sameLeg = a.node[r] === b.node[r] && a.target[r] === b.target[r];
      if (sameLeg && a.target[r] >= 0) return {...person, ratio: a.ratio[r] + (b.ratio[r] - a.ratio[r]) * t};
      if (a.target[r] >= 0 && b.node[r] === a.target[r]) return {...person, ratio: a.ratio[r] + (1 - a.ratio[r]) * t};
      if (t < 0.5 || sameLeg) return person;
      return {...person, node: this.ids[b.node[r]], target: b.target[r] >= 0 ? this.ids[b.target[r]] : null,
        ratio: b.ratio[r], status: STATUS_ORDER[b.status[r]]};
    });
    return result;
  }
}

// ---------------------------------------------------------------------------------------------
// Player: where the playhead is and whether it follows live data
// ---------------------------------------------------------------------------------------------

export class TimelinePlayer {
  constructor() {
    this.live = true;
    this.playing = false;
    this.speed = 1;
    this.second = 0;
  }

  position(recorder) {
    if (this.live || !recorder.length) return recorder.lastSecond;
    return Math.min(recorder.lastSecond, Math.max(recorder.firstSecond, this.second));
  }

  seek(second, recorder) {
    if (!recorder.length) return;
    this.second = Math.min(recorder.lastSecond, Math.max(recorder.firstSecond, second));
    this.live = false;
  }

  /** Step to the previous/next recorded frame. */
  step(direction, recorder) {
    if (!recorder.length) return;
    this.playing = false;
    const position = this.position(recorder);
    let i = recorder.indexAt(position);
    if (direction < 0 && recorder.frames[i].second === position) i -= 1;
    if (direction > 0) i += 1;
    i = Math.max(0, Math.min(recorder.length - 1, i));
    this.seek(recorder.frames[i].second, recorder);
  }

  /** Starts playback; from the beginning when already at the end or live. */
  play(recorder) {
    if (recorder.length < 2) return;
    if (this.live || this.position(recorder) >= recorder.lastSecond) this.second = recorder.firstSecond;
    this.live = false;
    this.playing = true;
  }

  pause() { this.playing = false; }

  goLive() { this.live = true; this.playing = false; }

  /** Advances playback by `dt` real seconds. Catching up with the newest frame returns to live. */
  tick(dt, recorder) {
    if (!this.playing || this.live) return false;
    this.second += dt * this.speed;
    if (this.second >= recorder.lastSecond) this.goLive();
    return true;
  }
}

// ---------------------------------------------------------------------------------------------
// Panel (DOM)
// ---------------------------------------------------------------------------------------------

/**
 * Wires the timeline controls, the population chart and the event list.
 * `onChange()` is called whenever the map should redraw (playhead moved or live/replay switched).
 */
export class TimelinePanel {
  constructor(recorder, player, {onChange}) {
    const $ = id => document.getElementById(id);
    this.el = {
      root: $('timeline'), chart: $('tl-chart'), range: $('tl-range'), current: $('tl-current'), end: $('tl-end'),
      play: $('tl-play'), back: $('tl-back'), next: $('tl-next'), start: $('tl-start'), live: $('tl-live'),
      speed: $('tl-speed'), caption: $('tl-caption'), stats: $('tl-stats'), events: $('tl-events'), banner: $('replay-banner'),
      empty: $('tl-empty'),
    };
    this.recorder = recorder;
    this.player = player;
    this.onChange = onChange;
    this.timer = null;
    this.eventsShown = -1;
    player.speed = Number(this.el.speed.value) || 1;
    this.bind();
    this.refresh();
  }

  get replaying() { return !this.player.live && this.recorder.length > 0; }

  bind() {
    const {el, player, recorder} = this;
    el.play.addEventListener('click', () => {
      if (player.playing) player.pause(); else player.play(recorder);
      this.changed();
      if (player.playing) this.loop();
    });
    el.back.addEventListener('click', () => { player.step(-1, recorder); this.changed(); });
    el.next.addEventListener('click', () => { player.step(1, recorder); this.changed(); });
    el.start.addEventListener('click', () => { player.pause(); player.seek(recorder.firstSecond, recorder); this.changed(); });
    el.live.addEventListener('click', () => { player.goLive(); this.changed(); });
    el.speed.addEventListener('change', () => { player.speed = Number(el.speed.value) || 1; });
    el.range.addEventListener('input', () => { player.pause(); player.seek(Number(el.range.value), recorder); this.changed(); });
    let dragging = false;
    const seekFromChart = event => {
      if (!recorder.length) return;
      const rect = el.chart.getBoundingClientRect();
      const {left, right} = this.chartBounds(rect.width);
      const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left - left) / (right - left)));
      player.pause();
      player.seek(recorder.firstSecond + fraction * (recorder.lastSecond - recorder.firstSecond), recorder);
      this.changed();
    };
    el.chart.addEventListener('pointerdown', event => { dragging = true; try { el.chart.setPointerCapture(event.pointerId); } catch { /* optional */ } seekFromChart(event); });
    el.chart.addEventListener('pointermove', event => { if (dragging) seekFromChart(event); });
    el.chart.addEventListener('pointerup', () => { dragging = false; });
    el.chart.addEventListener('pointercancel', () => { dragging = false; });
    if (typeof ResizeObserver === 'function') new ResizeObserver(() => this.drawChart()).observe(el.chart);
  }

  /** Playhead or mode changed by the user. */
  changed() { this.refresh(); this.onChange(); }

  /** Playback clock: about 30 redraws per second, advancing by real elapsed time. */
  loop() {
    if (this.timer) return;
    let previous = performance.now();
    const step = () => {
      const now = performance.now();
      // Capped so a tab that was hidden does not jump far ahead when it comes back.
      const dt = Math.min(1, (now - previous) / 1000);
      previous = now;
      this.player.tick(dt, this.recorder);
      this.refresh();
      this.onChange();
      this.timer = this.player.playing ? setTimeout(step, 33) : null;
    };
    this.timer = setTimeout(step, 33);
  }

  /** Re-reads the recorder and player into the controls, chart, stats and event list. */
  refresh() {
    const {el, recorder, player} = this;
    const has = recorder.length > 0;
    const position = player.position(recorder);
    el.empty.hidden = recorder.length >= 2;
    el.range.disabled = recorder.length < 2;
    el.range.min = String(recorder.firstSecond);
    el.range.max = String(Math.max(recorder.lastSecond, recorder.firstSecond + 1));
    el.range.value = String(Math.round(position));
    el.current.textContent = has ? clock(position) : '--:--';
    el.end.textContent = has ? clock(recorder.lastSecond) : '--:--';
    el.play.textContent = player.playing ? t('Ⅱ 일시정지','Ⅱ Pause') : t('▶ 기록 재생','▶ Play recording');
    el.play.disabled = recorder.length < 2;
    el.back.disabled = !has || position <= recorder.firstSecond;
    el.next.disabled = !has || player.live;
    el.start.disabled = !has;
    el.live.classList.toggle('active', player.live);
    el.live.setAttribute('aria-pressed', String(player.live));
    el.live.textContent = player.live ? t('● 실시간','● Live') : t('● 실시간으로','● Return to live');
    el.caption.textContent = has
      ? t(`기록 ${recorder.length}장면 · 모의 ${clock(recorder.firstSecond)}–${clock(recorder.lastSecond)} · 이 브라우저 탭에만 보관하며 새로고침·초기화하면 지워집니다.`,
        `${recorder.length} frames · simulation ${clock(recorder.firstSecond)}–${clock(recorder.lastSecond)} · saved in this tab until refresh or reset.`)
      : t('실시간 진행을 이 탭에서 기록합니다. 초기화 후 자동 진행을 누르면 처음부터 기록됩니다.','This tab records live progress. Select Reset, then Run to record from the start.');
    el.banner.hidden = !this.replaying;
    if (this.replaying) el.banner.textContent = t(`기록 재생 중 · 모의 ${clock(position)} · 현재 상황이 아닙니다`,`Playing a recording · simulation ${clock(position)}`);
    this.renderStats(position);
    this.renderEvents(position);
    this.drawChart();
  }

  renderStats(position) {
    const {recorder} = this;
    const frame = recorder.length ? recorder.frames[recorder.indexAt(position)] : null;
    const counts = frame?.counts;
    const cells = [
      [t('대피 완료','Evacuated'), counts ? counts.EVACUATED : '—', 'EVACUATED'],
      [t('이동 중','Moving'), counts ? counts.MOVING : '—', 'MOVING'],
      [t('대기·정체','Waiting or queued'), counts ? counts.WAITING + counts.QUEUED : '—', 'QUEUED'],
      [t('경로 없음·고립','No route or blocked'), counts ? counts.NO_ROUTE + counts.BLOCKED_IN_TRANSIT : '—', 'NO_ROUTE'],
    ];
    this.el.stats.replaceChildren(...cells.map(([label, value, status]) => {
      const cell = document.createElement('div');
      cell.className = 'tl-stat';
      const dot = document.createElement('i');
      dot.className = 'tl-dot status-' + status;
      const name = document.createElement('span');
      name.textContent = label;
      const number = document.createElement('strong');
      number.textContent = typeof value === 'number' ? t(`${value}명`,String(value)) : value;
      cell.append(dot, name, number);
      return cell;
    }));
  }

  renderEvents(position) {
    const items = this.recorder.events;
    const list = this.el.events;
    const language = getLanguage();
    const changed = this.eventsShown !== items.length || this.eventsLanguage !== language;
    this.eventsShown = items.length;
    this.eventsLanguage = language;
    if (!items.length) {
      if (changed) list.replaceChildren(Object.assign(document.createElement('li'), {className: 'tl-empty', textContent: t('기록된 사건이 아직 없습니다.','No events recorded yet.')}));
      return;
    }
    if (changed) {
      list.replaceChildren(...items.slice(-80).reverse().map(item => {
        const row = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'tl-event';
        button.dataset.second = String(item.second);
        const time = document.createElement('time');
        time.textContent = clock(item.second);
        const dot = document.createElement('i');
        dot.className = 'tl-dot kind-' + item.kind;
        const text = document.createElement('span');
        text.textContent = t(item.text,item.english);
        button.append(time, dot, text);
        button.addEventListener('click', () => {
          this.player.pause();
          this.player.seek(item.second, this.recorder);
          if (item.floor && this.onFloor) this.onFloor(item.floor);
          this.changed();
        });
        row.append(button);
        return row;
      }));
    }
    for (const button of list.querySelectorAll('.tl-event')) button.classList.toggle('future', Number(button.dataset.second) > position);
  }

  chartBounds(width) { return {left: 44, right: width - 12}; }

  drawChart() {
    const canvas = this.el.chart;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const {recorder, player} = this;
    const {left, right} = this.chartBounds(width);
    const top = 16;
    const bottom = height - 20;
    ctx.font = '11px system-ui, "Noto Sans KR", sans-serif';
    if (recorder.length < 2) {
      ctx.fillStyle = '#7b909c';
      ctx.textAlign = 'center';
      ctx.fillText(t('장면이 두 개 이상 기록되면 인원 변화와 사건이 여기에 그려집니다.','Record two or more frames to see resident counts and events.'), width / 2, height / 2);
      return;
    }
    const first = recorder.firstSecond;
    const span = Math.max(1, recorder.lastSecond - first);
    const total = recorder.frames[recorder.length - 1].total || 1;
    const x = second => left + (second - first) / span * (right - left);
    const y = people => bottom - people / total * (bottom - top);

    ctx.strokeStyle = '#e3eaef';
    ctx.fillStyle = '#7b909c';
    ctx.textAlign = 'right';
    for (const share of [0, 0.5, 1]) {
      const lineY = y(total * share);
      ctx.beginPath(); ctx.moveTo(left, lineY); ctx.lineTo(right, lineY); ctx.stroke();
      const count = Math.round(total * share);
      ctx.fillText(t(`${count}명`,String(count)), left - 6, lineY + 4);
    }

    // Stacked bands, bottom to top: evacuated, moving, queued, waiting, no route, blocked in transit.
    let lower = recorder.frames.map(() => 0);
    for (const status of STATUS_ORDER) {
      const upper = recorder.frames.map((frame, i) => lower[i] + frame.counts[status]);
      ctx.beginPath();
      recorder.frames.forEach((frame, i) => (i ? ctx.lineTo(x(frame.second), y(upper[i])) : ctx.moveTo(x(frame.second), y(upper[i]))));
      for (let i = recorder.frames.length - 1; i >= 0; i -= 1) ctx.lineTo(x(recorder.frames[i].second), y(lower[i]));
      ctx.closePath();
      ctx.fillStyle = RESIDENT_STATES[status].color;
      ctx.globalAlpha = status === 'EVACUATED' ? 0.85 : 0.7;
      ctx.fill();
      ctx.globalAlpha = 1;
      lower = upper;
    }

    // Event markers along the top edge.
    for (const item of recorder.events) {
      const markerX = x(item.second);
      ctx.fillStyle = EVENT_KINDS[item.kind]?.color || '#5b6b82';
      ctx.beginPath(); ctx.moveTo(markerX - 4, 2); ctx.lineTo(markerX + 4, 2); ctx.lineTo(markerX, 10); ctx.closePath(); ctx.fill();
    }

    // Playhead.
    const position = player.position(recorder);
    const headX = x(position);
    ctx.strokeStyle = player.live ? '#c43b41' : '#14213d';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(headX, top - 4); ctx.lineTo(headX, bottom); ctx.stroke();
    ctx.lineWidth = 1;
    ctx.fillStyle = '#7b909c';
    ctx.textAlign = 'left';
    ctx.fillText(clock(first), left, height - 5);
    ctx.textAlign = 'right';
    ctx.fillText(clock(recorder.lastSecond), right, height - 5);
  }
}
