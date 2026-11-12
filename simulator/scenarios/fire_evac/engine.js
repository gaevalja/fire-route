/* One-second presentation of simultaneous one-minute scenario updates. Load config.js first. */
(function (global) {
  "use strict";

  const CFG = global.FireEvacConfig;
  if (!CFG) throw new Error("config.js must be loaded before engine.js");

  const fireEdges = new Map();
  const smokeIn = new Map();
  const zoneTemplates = [];
  const corridorSmokeId = (floor) => `F${floor}-C`;

  function addZone(id, type, floor, label) {
    zoneTemplates.push({ id, type, floor, label, size: CFG.ZONE_SIZE[type] });
    fireEdges.set(id, new Set());
    if (type !== "corridor") smokeIn.set(id, new Set());
  }

  function fireLink(a, b) {
    fireEdges.get(a).add(b);
    fireEdges.get(b).add(a);
  }

  function smokeLink(a, b) {
    smokeIn.get(a).add(b);
    smokeIn.get(b).add(a);
  }

  function smokeOneWay(from, to) {
    smokeIn.get(to).add(from);
  }

  function buildTopology() {
    for (let floor = 1; floor <= CFG.FLOORS; floor += 1) {
      const roomCount = floor === 1 ? CFG.ROOMS_ON_FIRST_FLOOR : CFG.ROOMS_ON_UPPER_FLOOR;
      for (let i = 1; i <= roomCount; i += 1) {
        addZone(`F${floor}-R${i}`, "room", floor, `방 ${i}`);
      }
      if (floor === 1) {
        addZone("F1-L", "lobby", floor, "로비");
      } else {
        for (let i = 1; i <= CFG.CORRIDOR_SEGMENTS; i += 1) {
          addZone(`F${floor}-C${i}`, "corridor", floor, `복도 ${i}`);
        }
        smokeIn.set(corridorSmokeId(floor), new Set());
      }
      addZone(`F${floor}-SA`, "stair", floor, "비상계단 A");
      addZone(`F${floor}-SB`, "stair", floor, "비상계단 B");
      addZone(`F${floor}-E`, "elevator", floor, "엘리베이터");
    }
    addZone("F11-ROOF", "roof", CFG.ROOF_FLOOR, "옥상");

    // First floor: four rooms and both stairs/elevator open into one lobby.
    for (const id of ["F1-R1", "F1-R2", "F1-R3", "F1-R4", "F1-SA", "F1-SB", "F1-E"]) {
      fireLink("F1-L", id);
      smokeLink("F1-L", id);
    }

    // Standard floors: five corridor slices. Top rooms 1..5 and bottom
    // rooms 6,7,elevator,8,9 align with slices 1..5 respectively.
    for (let floor = 2; floor <= CFG.FLOORS; floor += 1) {
      const smokeCorridor = corridorSmokeId(floor);
      for (let i = 1; i <= CFG.CORRIDOR_SEGMENTS; i += 1) {
        const corridor = `F${floor}-C${i}`;
        const topRoom = `F${floor}-R${i}`;
        fireLink(corridor, topRoom);
        smokeLink(smokeCorridor, topRoom);
        if (i < CFG.CORRIDOR_SEGMENTS) fireLink(corridor, `F${floor}-C${i + 1}`);
      }
      const lower = ["R6", "R7", "E", "R8", "R9"];
      for (let i = 0; i < lower.length; i += 1) {
        const id = `F${floor}-${lower[i]}`;
        fireLink(`F${floor}-C${i + 1}`, id);
        smokeLink(smokeCorridor, id);
      }
      fireLink(`F${floor}-C1`, `F${floor}-SA`);
      fireLink(`F${floor}-C5`, `F${floor}-SB`);
      smokeLink(smokeCorridor, `F${floor}-SA`);
      smokeLink(smokeCorridor, `F${floor}-SB`);
    }

    // Fire may spread in either vertical direction. Smoke may rise only.
    // The elevator has intentionally no inter-floor edge in either graph.
    for (let floor = 1; floor < CFG.FLOORS; floor += 1) {
      for (const side of ["A", "B"]) {
        const lower = `F${floor}-S${side}`;
        const upper = `F${floor + 1}-S${side}`;
        fireLink(lower, upper);
        smokeOneWay(lower, upper);
      }
    }
    for (const side of ["A", "B"]) {
      fireLink(`F10-S${side}`, "F11-ROOF");
      smokeOneWay(`F10-S${side}`, "F11-ROOF");
    }
  }
  buildTopology();

  function clamp(value) {
    return Math.min(CFG.MAX_LEVEL, Math.max(0, value));
  }

  function normalizeSeed(seed) {
    if (Number.isFinite(Number(seed))) {
      return (Math.trunc(Number(seed)) >>> 0) || 1;
    }
    const text = String(seed == null ? Date.now() : seed);
    let hash = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0 || 1;
  }

  function nextRandom(rngState) {
    const next = (Math.imul(1664525, rngState) + 1013904223) >>> 0;
    return { state: next, value: next / 4294967296 };
  }

  function createSimulation({ seed = Date.now(), wind = CFG.DEFAULT_WIND } = {}) {
    const selectedWind = Number(wind);
    if (!CFG.WIND_OPTIONS.includes(selectedWind)) {
      throw new RangeError(`Wind must be one of ${CFG.WIND_OPTIONS.join(", ")} m/s`);
    }
    const normalizedSeed = normalizeSeed(seed);
    const zones = {};
    for (const template of zoneTemplates) {
      zones[template.id] = { ...template, fire: 0, smoke: 0, collapsed: false };
    }
    const rooms = zoneTemplates.filter((zone) => zone.type === "room");
    const draw = nextRandom(normalizedSeed);
    const ignitionId = rooms[Math.floor(draw.value * rooms.length)].id;
    zones[ignitionId].fire = CFG.INITIAL_FIRE;
    return {
      minute: 0,
      second: 0,
      seed: normalizedSeed,
      wind: selectedWind,
      ignitionId,
      zones,
      ended: false,
      rngState: draw.state,
      events: [{ minute: 0, second: 0, type: "ignition", zoneId: ignitionId, message: `${zones[ignitionId].floor}층 ${zones[ignitionId].label}에서 화재 발생` }]
    };
  }

  function currentSmoke(state, smokeId) {
    if (smokeId.endsWith("-C")) return state.zones[`${smokeId}1`].smoke;
    return state.zones[smokeId].smoke;
  }

  function currentFireForSmoke(state, smokeId) {
    if (!smokeId.endsWith("-C")) return state.zones[smokeId].fire;
    let sum = 0;
    for (let i = 1; i <= CFG.CORRIDOR_SEGMENTS; i += 1) sum += state.zones[`${smokeId}${i}`].fire;
    return sum / CFG.CORRIDOR_SEGMENTS;
  }

  function nextFireForSmoke(nextZones, smokeId) {
    if (!smokeId.endsWith("-C")) return nextZones[smokeId].fire;
    let sum = 0;
    for (let i = 1; i <= CFG.CORRIDOR_SEGMENTS; i += 1) sum += nextZones[`${smokeId}${i}`].fire;
    return sum / CFG.CORRIDOR_SEGMENTS;
  }

  function calculateFire(state, zone, windFactor) {
    const neighbors = fireEdges.get(zone.id);
    let maxNeighborFire = 0;
    for (const id of neighbors) maxNeighborFire = Math.max(maxNeighborFire, state.zones[id].fire);
    const localGrowth = zone.fire > 0 ? CFG.FIRE_GROWTH_PER_MINUTE / zone.size : 0;
    const incoming = maxNeighborFire * CFG.FIRE_SPREAD_PER_MINUTE * windFactor / zone.size;
    return clamp(zone.fire + localGrowth + incoming);
  }

  function calculateSmoke(state, nextZones, smokeId, windFactor) {
    const oldSmoke = currentSmoke(state, smokeId);
    let maxNeighborSmoke = 0;
    let maxNeighborFire = 0;
    for (const id of smokeIn.get(smokeId)) {
      maxNeighborSmoke = Math.max(maxNeighborSmoke, currentSmoke(state, id));
      maxNeighborFire = Math.max(maxNeighborFire, currentFireForSmoke(state, id));
    }
    const size = smokeId.endsWith("-C") ? CFG.ZONE_SIZE.corridor * CFG.CORRIDOR_SEGMENTS : state.zones[smokeId].size;
    const generated = currentFireForSmoke(state, smokeId) * CFG.SMOKE_GENERATION_PER_FIRE / size;
    const transportedSmoke = Math.max(0, maxNeighborSmoke - oldSmoke) * CFG.SMOKE_SPREAD_PER_MINUTE * windFactor;
    const smokeFromNeighborFire = maxNeighborFire * CFG.SMOKE_DIRECT_FIRE_TRANSFER * windFactor;
    const incoming = Math.max(transportedSmoke, smokeFromNeighborFire);
    const fireCap = nextFireForSmoke(nextZones, smokeId) + CFG.SMOKE_ABOVE_FIRE_CAP;
    return Math.min(clamp(oldSmoke + generated + incoming), fireCap);
  }

  function collapseProbability(fire) {
    if (fire < CFG.COLLAPSE_FIRE_THRESHOLD) return 0;
    const exposure = (fire - CFG.COLLAPSE_FIRE_THRESHOLD) / (CFG.MAX_LEVEL - CFG.COLLAPSE_FIRE_THRESHOLD);
    return CFG.COLLAPSE_MAX_PROBABILITY * exposure * exposure;
  }

  function advanceOneMinute(state) {
    if (state.ended) return state;
    const windFactor = CFG.WIND_MULTIPLIER[state.wind];
    const minute = state.minute + 1;
    const nextZones = {};
    const newEvents = [];
    let rngState = state.rngState;
    let collapsedCount = Object.values(state.zones).filter((zone) => zone.collapsed).length;

    // All hazard calculations below read state.zones, never nextZones as a source.
    for (const template of zoneTemplates) {
      const oldZone = state.zones[template.id];
      const fire = calculateFire(state, oldZone, windFactor);
      nextZones[template.id] = { ...oldZone, fire };
      if (oldZone.fire === 0 && fire > 0) {
        newEvents.push({ minute, second: minute * CFG.SECONDS_PER_MINUTE, type: "spread", zoneId: template.id, message: `${template.floor}층 ${template.label}에 불 확산` });
      }
    }
    for (const smokeId of smokeIn.keys()) {
      const smoke = calculateSmoke(state, nextZones, smokeId, windFactor);
      if (smokeId.endsWith("-C")) {
        for (let i = 1; i <= CFG.CORRIDOR_SEGMENTS; i += 1) nextZones[`${smokeId}${i}`].smoke = smoke;
      } else {
        nextZones[smokeId].smoke = smoke;
      }
    }
    for (const template of zoneTemplates) {
      const zone = nextZones[template.id];
      if (collapsedCount >= CFG.MAX_COLLAPSED_ZONES) break;
      if (zone.collapsed || zone.type === "stair" || zone.type === "elevator") continue;
      const probability = collapseProbability(state.zones[template.id].fire);
      if (probability === 0) continue;
      const draw = nextRandom(rngState);
      rngState = draw.state;
      if (draw.value < probability) {
        zone.collapsed = true;
        collapsedCount += 1;
        newEvents.push({ minute, second: minute * CFG.SECONDS_PER_MINUTE, type: "collapse", zoneId: zone.id, message: `${zone.floor}층 ${zone.label} 붕괴` });
      }
    }

    const ended = zoneTemplates.every((zone) => nextZones[zone.id].fire >= CFG.MAX_LEVEL);
    if (ended) newEvents.push({ minute, second: minute * CFG.SECONDS_PER_MINUTE, type: "end", zoneId: null, message: "모든 구역의 불 수치가 100에 도달하여 시나리오 종료" });
    const events = state.events.concat(newEvents).slice(-CFG.EVENT_HISTORY_LIMIT);
    return { ...state, minute, zones: nextZones, ended, rngState, events };
  }

  // Hazard levels move smoothly between full-minute calculations. A collapse,
  // spread log entry, and completion flag become visible only at the minute
  // boundary. Thus each 60th second is exactly the original one-minute state.
  function stepSimulation(state) {
    if (state.ended) return state;
    const phase = state.second % CFG.SECONDS_PER_MINUTE;
    const anchorZones = phase === 0 ? state.zones : state._anchorZones;
    const target = phase === 0 ? advanceOneMinute(state) : state._minuteTarget;
    const second = state.second + CFG.TIME_STEP_SECONDS;
    if (second % CFG.SECONDS_PER_MINUTE === 0) {
      return { ...target, second, minute: second / CFG.SECONDS_PER_MINUTE };
    }
    const progress = (second % CFG.SECONDS_PER_MINUTE) / CFG.SECONDS_PER_MINUTE;
    const zones = {};
    for (const template of zoneTemplates) {
      const before = anchorZones[template.id];
      const after = target.zones[template.id];
      zones[template.id] = {
        ...before,
        fire: before.fire + (after.fire - before.fire) * progress,
        smoke: before.smoke + (after.smoke - before.smoke) * progress
      };
    }
    return { ...state, second, zones, _anchorZones: anchorZones, _minuteTarget: target };
  }

  function getFloorZones(state, floor) {
    return zoneTemplates.filter((zone) => zone.floor === Number(floor)).map((zone) => state.zones[zone.id]);
  }

  function getStats(state) {
    const zones = Object.values(state.zones);
    const totalZones = zones.length;
    const totalFire = zones.reduce((sum, zone) => sum + zone.fire, 0);
    const totalSmoke = zones.reduce((sum, zone) => sum + zone.smoke, 0);
    return {
      totalZones,
      burningZones: zones.filter((zone) => zone.fire > 0).length,
      collapsedZones: zones.filter((zone) => zone.collapsed).length,
      avgFire: totalFire / totalZones,
      avgSmoke: totalSmoke / totalZones,
      maxFire: Math.max(...zones.map((zone) => zone.fire)),
      maxSmoke: Math.max(...zones.map((zone) => zone.smoke)),
      completedPercent: totalFire / totalZones,
      finished: state.ended
    };
  }

  global.FireEvacEngine = Object.freeze({
    createSimulation,
    stepSimulation,
    getFloorZones,
    getStats,
    collapseProbability
  });
})(typeof window !== "undefined" ? window : globalThis);
