/* Visual controller. Simulation rules and tunable numbers live in config.js / engine.js. */
(() => {
  'use strict';

  const engine = window.FireEvacEngine;
  if (!engine) {
    document.body.innerHTML = '<p style="color:white;padding:2rem">시뮬레이션 엔진을 불러오지 못했습니다. engine.js 파일을 확인하세요.</p>';
    return;
  }

  const $ = (id) => document.getElementById(id);
  const ui = {
    wind: $('wind-select'), seed: $('seed-input'), randomSeed: $('random-seed'), speed: $('speed-select'),
    play: $('play-button'), playIcon: $('play-icon'), playLabel: $('play-label'), step: $('step-button'), reset: $('reset-button'),
    status: $('run-status'), statusBox: document.querySelector('.header-status'),
    time: $('metric-time'), origin: $('metric-origin'), burning: $('metric-burning'), collapsed: $('metric-collapsed'),
    progress: $('metric-progress'), progressFill: $('progress-fill'),
    floorTitle: $('floor-title'), floorDescription: $('floor-description'), floorTabs: $('floor-tabs'),
    floorDown: $('floor-down'), floorUp: $('floor-up'), floorplan: $('floorplan'),
    inspector: $('zone-inspector'), events: $('event-list')
  };

  let simulation;
  let floor = 2;
  let layer = 'both';
  let selectedId = null;
  let timer = null;
  let recentEvents = [];

  function formatNumber(value) {
    const number = Number(value) || 0;
    return Number.isInteger(number) ? String(number) : number.toFixed(1);
  }

  function formatClock(totalSeconds) {
    const seconds = Math.max(0, Math.trunc(Number(totalSeconds) || 0));
    return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
  }

  function clamp(value, low, high) { return Math.min(high, Math.max(low, value)); }

  function zone(id) { return simulation.zones[id]; }

  function readableType(type) {
    return {room:'방',corridor:'복도',lobby:'로비',stair:'비상계단',elevator:'엘리베이터',roof:'옥상'}[type] || type;
  }

  function displayName(item) {
    if (!item) return '알 수 없음';
    if (item.type === 'room') return `${item.floor}층 ${item.label}`;
    if (item.type === 'roof') return '11층 옥상';
    return `${item.floor}층 ${item.label}`;
  }

  function addEvent(second, message, priority = false) {
    recentEvents.unshift({second, message});
    if (recentEvents.length > 40) recentEvents.length = 40;
    if (priority) recentEvents = recentEvents.slice(0, 40);
  }

  function create() {
    stop();
    const seed = clamp(Math.trunc(Number(ui.seed.value) || 1), 1, 2147483647);
    const wind = Number(ui.wind.value);
    ui.seed.value = seed;
    simulation = engine.createSimulation({seed, wind});
    selectedId = null;
    recentEvents = [];
    addEvent(0, `${displayName(zone(simulation.ignitionId))}에서 화재가 시작되었습니다.`, true);
    addEvent(0, `풍속 ${wind} m/s의 시나리오를 생성했습니다.`);
    render();
  }

  function stop() {
    if (timer !== null) clearInterval(timer);
    timer = null;
  }

  function start() {
    if (simulation.ended || timer !== null) return;
    timer = setInterval(advance, Number(ui.speed.value));
    renderStatus();
  }

  function toggle() { timer === null ? start() : (stop(), renderStatus()); }

  function advance() {
    if (simulation.ended) { stop(); render(); return; }
    const before = simulation;
    simulation = engine.stepSimulation(before);
    recordChanges(before, simulation);
    if (simulation.ended) {
      stop();
      addEvent(simulation.second, '모든 구역의 불 수치가 100이 되어 시나리오가 종료되었습니다.', true);
    }
    render();
  }

  function recordChanges(before, after) {
    const newFire = [];
    const newCollapse = [];
    for (const item of Object.values(after.zones)) {
      const old = before.zones[item.id];
      if (!old) continue;
      if (old.fire <= 0 && item.fire > 0) newFire.push(item);
      if (!old.collapsed && item.collapsed) newCollapse.push(item);
    }
    if (newFire.length) {
      const examples = newFire.slice(0, 2).map(displayName).join(', ');
      addEvent(after.second, `${examples}${newFire.length > 2 ? ` 외 ${newFire.length - 2}곳` : ''}에 불이 확산됐습니다.`);
    }
    if (newCollapse.length) {
      const examples = newCollapse.slice(0, 2).map(displayName).join(', ');
      addEvent(after.second, `${examples}${newCollapse.length > 2 ? ` 외 ${newCollapse.length - 2}곳` : ''}이 붕괴됐습니다.`, true);
    }
    if (after.second > 0 && after.second % 600 === 0 && !newFire.length && !newCollapse.length) {
      addEvent(after.second, '건물 전체 상태를 갱신했습니다.');
    }
  }

  function renderStatus() {
    ui.statusBox.classList.toggle('running', timer !== null);
    ui.statusBox.classList.toggle('finished', simulation.ended);
    ui.status.textContent = simulation.ended ? '시나리오 종료' : timer !== null ? '재생 중' : simulation.second === 0 ? '준비 완료' : '일시 정지';
    ui.playIcon.textContent = timer !== null ? 'Ⅱ' : '▶';
    ui.playLabel.textContent = timer !== null ? '일시 정지' : '재생';
    ui.play.disabled = simulation.ended;
    ui.step.disabled = simulation.ended;
  }

  function renderMetrics() {
    const stats = engine.getStats(simulation);
    ui.time.textContent = formatClock(simulation.second);
    ui.origin.textContent = `발화: ${displayName(zone(simulation.ignitionId))}`;
    ui.burning.textContent = stats.burningZones;
    ui.collapsed.textContent = stats.collapsedZones;
    const progress = clamp(Number(stats.completedPercent ?? stats.avgFire) || 0, 0, 100);
    ui.progress.textContent = formatNumber(progress);
    ui.progressFill.style.width = `${progress}%`;
  }

  function renderFloorTabs() {
    const fragment = document.createDocumentFragment();
    for (let number = 1; number <= 11; number++) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = number === 11 ? '옥상' : `${number}F`;
      button.className = floor === number ? 'active' : '';
      button.setAttribute('aria-pressed', String(floor === number));
      button.addEventListener('click', () => selectFloor(number));
      fragment.append(button);
    }
    ui.floorTabs.replaceChildren(fragment);
    ui.floorDown.disabled = floor === 1;
    ui.floorUp.disabled = floor === 11;
  }

  function selectFloor(number) {
    floor = clamp(number, 1, 11);
    selectedId = null;
    renderFloorTabs();
    renderPlan();
    renderInspector();
  }

  function tileColors(item) {
    const fire = clamp(Number(item.fire) || 0, 0, 100);
    const smoke = clamp(Number(item.smoke) || 0, 0, 100);
    const prominentFire = layer === 'fire' || (layer === 'both' && fire >= smoke && fire > 0);
    const prominentSmoke = layer === 'smoke' || (layer === 'both' && !prominentFire && smoke > 0);
    if (prominentFire && fire > 0) {
      const alpha = 0.19 + fire / 155;
      return {bg:`linear-gradient(135deg, rgba(239,99,61,${alpha}),rgba(81,38,44,${alpha})),#26384a`,border:fire > 60 ? '#ff9c68' : '#be745a'};
    }
    if (prominentSmoke && smoke > 0) {
      const alpha = 0.17 + smoke / 170;
      return {bg:`linear-gradient(135deg, rgba(132,166,173,${alpha}),rgba(46,82,94,${alpha})),#26384a`,border:smoke > 60 ? '#aac7ca' : '#658e9c'};
    }
    return {bg:'#263e52',border:'#4b7180'};
  }

  function makeTile(id, column, row, rowSpan = 1, extraClass = '', door = '') {
    const item = zone(id);
    if (!item) return null;
    const button = document.createElement('button');
    const colors = tileColors(item);
    button.type = 'button';
    button.className = `zone zone-${item.type} ${extraClass} ${item.collapsed ? 'collapsed' : ''} ${selectedId === id ? 'selected' : ''}`;
    button.style.gridColumn = String(column);
    button.style.gridRow = rowSpan > 1 ? `${row} / span ${rowSpan}` : String(row);
    button.style.setProperty('--zone-bg', colors.bg);
    button.style.setProperty('--zone-border', colors.border);
    button.setAttribute('aria-label', `${displayName(item)}, 불 ${formatNumber(item.fire)}, 연기 ${formatNumber(item.smoke)}${item.collapsed ? ', 붕괴' : ''}`);
    const title = document.createElement('span');
    title.className = 'zone-title';
    title.textContent = item.label;
    const values = document.createElement('span');
    values.className = 'zone-values';
    const fire = document.createElement('span');
    fire.textContent = `불 ${formatNumber(item.fire)}`;
    const smoke = document.createElement('span');
    smoke.textContent = `연기 ${formatNumber(item.smoke)}`;
    values.append(fire, smoke);
    button.append(title, values);
    if (door) {
      const mark = document.createElement('i');
      mark.className = `zone-door ${door}`;
      mark.setAttribute('aria-hidden', 'true');
      button.append(mark);
    }
    button.addEventListener('click', () => { selectedId = id; renderPlan(); renderInspector(); });
    return button;
  }

  function renderPlan() {
    ui.floorTitle.textContent = floor === 11 ? '11층 옥상' : `${floor}층 평면도`;
    ui.floorDescription.textContent = floor === 11 ? '단일 옥상 구역 · 계단 A/B와 연결' : floor === 1 ? '방 4개 · 로비 1구역 · 출입구 2개 · 계단 A/B · 엘리베이터' : '방 9개 · 복도 5구역 · 계단 A/B · 엘리베이터';
    ui.floorplan.replaceChildren();
    if (floor === 11) {
      const roof = document.createElement('div');
      roof.className = 'roof-plan';
      const tile = makeTile('F11-ROOF', 1, 1, 1, 'roof-tile');
      if (tile) roof.append(tile);
      const stairs = document.createElement('div');
      stairs.className = 'roof-stairs';
      stairs.innerHTML = '<span>↑ 계단 A</span><span>계단 B ↑</span>';
      roof.append(stairs);
      ui.floorplan.append(roof);
      return;
    }
    const grid = document.createElement('div');
    grid.className = 'building-grid';
    const items = [];
    const add = (...args) => { const tile = makeTile(...args); if (tile) items.push(tile); };
    add(`F${floor}-SA`, 1, 1, 3, '', 'right');
    add(`F${floor}-SB`, 7, 1, 3, '', 'left');
    if (floor === 1) {
      add('F1-R1', 2, 1, 1, '', 'bottom');
      add('F1-R2', 3, 1, 1, '', 'bottom');
      add('F1-E', 4, 1, 1, '', 'bottom');
      add('F1-R3', 5, 1, 1, '', 'bottom');
      add('F1-R4', 6, 1, 1, '', 'bottom');
      add('F1-L', '2 / 7', 2, 2, 'lobby-tile');
      const exits = document.createElement('div');
      exits.className = 'lobby-exits';
      exits.innerHTML = '<span class="exit-marker">↓ 출입구 1</span><span class="exit-marker">↓ 출입구 2</span>';
      items.push(exits);
    } else {
      for (let room = 1; room <= 5; room++) add(`F${floor}-R${room}`, room + 1, 1, 1, '', 'bottom');
      for (let section = 1; section <= 5; section++) add(`F${floor}-C${section}`, section + 1, 2);
      add(`F${floor}-R6`, 2, 3, 1, '', 'top');
      add(`F${floor}-R7`, 3, 3, 1, '', 'top');
      add(`F${floor}-E`, 4, 3, 1, '', 'top');
      add(`F${floor}-R8`, 5, 3, 1, '', 'top');
      add(`F${floor}-R9`, 6, 3, 1, '', 'top');
    }
    grid.append(...items);
    ui.floorplan.append(grid);
  }

  function renderInspector() {
    ui.inspector.replaceChildren();
    const item = selectedId ? zone(selectedId) : null;
    if (!item) {
      const empty = document.createElement('div');
      empty.className = 'empty-state';
      empty.innerHTML = '<div class="empty-icon">⌖</div><strong>구역을 선택하세요</strong><p>평면도의 방, 복도, 계단을 누르면 현재 상태가 표시됩니다.</p>';
      ui.inspector.append(empty);
      return;
    }
    const heading = document.createElement('div');
    heading.className = 'selected-zone-heading';
    const name = document.createElement('strong'); name.textContent = displayName(item);
    const badge = document.createElement('span'); badge.className = 'zone-badge'; badge.textContent = readableType(item.type);
    heading.append(name, badge);
    ui.inspector.append(heading);
    for (const [label, value, kind] of [['불',item.fire,'fire'],['연기',item.smoke,'smoke']]) {
      const block = document.createElement('div'); block.className = 'readout';
      const line = document.createElement('div'); line.className = 'readout-label';
      const labelEl = document.createElement('span'); labelEl.textContent = `${label} 수치`;
      const valueEl = document.createElement('strong'); valueEl.textContent = `${formatNumber(value)} / 100`;
      line.append(labelEl, valueEl);
      const track = document.createElement('div'); track.className = `readout-track ${kind}`;
      const fill = document.createElement('div'); fill.style.width = `${clamp(value,0,100)}%`;
      track.append(fill); block.append(line, track); ui.inspector.append(block);
    }
    const info = document.createElement('div'); info.className = 'zone-info-line';
    let smokeCap = item.fire + 30;
    let note = `공간 크기 ${formatNumber(item.size)} · ${item.collapsed ? '붕괴: 이동 불가' : '이동 가능'}`;
    if (item.type === 'corridor') {
      const corridors = Array.from({length:5}, (_,i) => zone(`F${floor}-C${i+1}`)).filter(Boolean);
      smokeCap = corridors.reduce((sum, c) => sum + c.fire, 0) / corridors.length + 30;
      note += '<br>연기: 이 층 복도 전체가 같은 수치';
    }
    info.innerHTML = `${note}<br>현재 연기 상한 ${formatNumber(Math.min(100,smokeCap))}`;
    ui.inspector.append(info);
  }

  function renderEvents() {
    ui.events.replaceChildren();
    if (!recentEvents.length) {
      const empty = document.createElement('p'); empty.className = 'event-empty'; empty.textContent = '아직 기록된 변화가 없습니다.'; ui.events.append(empty); return;
    }
    for (const event of recentEvents.slice(0, 12)) {
      const block = document.createElement('div'); block.className = 'event-item';
      const time = document.createElement('div'); time.className = 'event-time'; time.textContent = formatClock(event.second);
      const text = document.createElement('div'); text.className = 'event-text'; text.textContent = event.message;
      block.append(time, text); ui.events.append(block);
    }
  }

  function render() { renderStatus(); renderMetrics(); renderFloorTabs(); renderPlan(); renderInspector(); renderEvents(); }

  ui.play.addEventListener('click', toggle);
  ui.step.addEventListener('click', advance);
  ui.reset.addEventListener('click', create);
  ui.randomSeed.addEventListener('click', () => { ui.seed.value = Math.floor(Math.random() * 2147483646) + 1; create(); });
  ui.wind.addEventListener('change', create);
  ui.seed.addEventListener('change', create);
  ui.speed.addEventListener('change', () => { if (timer !== null) { stop(); start(); } });
  ui.floorDown.addEventListener('click', () => selectFloor(floor - 1));
  ui.floorUp.addEventListener('click', () => selectFloor(floor + 1));
  for (const button of document.querySelectorAll('[data-layer]')) {
    button.addEventListener('click', () => {
      layer = button.dataset.layer;
      for (const other of document.querySelectorAll('[data-layer]')) {
        other.classList.toggle('active', other === button);
        other.setAttribute('aria-pressed', String(other === button));
      }
      renderPlan();
    });
  }

  create();
})();
