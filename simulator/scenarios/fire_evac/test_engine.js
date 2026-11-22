/* Run with: node test_engine.js */
const assert = require("node:assert/strict");
require("./config.js");
require("./engine.js");

const { createSimulation, stepSimulation, fireGrowthMultiplier } = globalThis.FireEvacEngine;
const cap = globalThis.FireEvacConfig.SMOKE_ABOVE_FIRE_CAP;
const roofCap = globalThis.FireEvacConfig.ROOF_SMOKE_CAP;

function blank(seed = 17) {
  const state = createSimulation({ seed, wind: 5 });
  state.zones[state.ignitionId].fire = 0;
  return state;
}

function testTopologyAndDirection() {
  const state = blank();
  assert.equal(Object.keys(state.zones).length, 162);
  assert.match(state.ignitionId, /^F(?:[1-9]|10)-R\d+$/);

  state.zones["F5-SA"].fire = 20;
  state.zones["F5-SA"].smoke = 20;
  const next = stepSimulation(state);
  assert(next.zones["F4-SA"].fire > 0, "fire can descend stairs");
  assert(next.zones["F6-SA"].fire > 0, "fire can ascend stairs");
  assert.equal(next.zones["F4-SA"].smoke, 0, "smoke does not descend stairs");
  assert(next.zones["F6-SA"].smoke > 0, "smoke ascends stairs");

  const elevator = blank();
  elevator.zones["F5-E"].fire = 20;
  elevator.zones["F5-E"].smoke = 20;
  const elevatorNext = stepSimulation(elevator);
  assert.equal(elevatorNext.zones["F4-E"].fire, 0);
  assert.equal(elevatorNext.zones["F6-E"].fire, 0);
  assert.equal(elevatorNext.zones["F4-E"].smoke, 0);
  assert.equal(elevatorNext.zones["F6-E"].smoke, 0);
}

function testSmokeCapAndCompletion() {
  let state = createSimulation({ seed: 12345, wind: 10 });
  let previousFire = Object.fromEntries(Object.values(state.zones).map((z) => [z.id, z.fire]));
  while (!state.ended && state.second < 12000) {
    state = stepSimulation(state);
    for (const zone of Object.values(state.zones)) {
      assert(zone.fire >= previousFire[zone.id]);
      assert(zone.fire >= 0 && zone.fire <= 100);
      assert(zone.smoke >= 0 && zone.smoke <= 100);
      if (zone.type === "stair" || zone.type === "elevator") assert.equal(zone.collapsed, false);
      const localFire = zone.type === "corridor"
        ? [1, 2, 3, 4, 5].reduce((sum, i) => sum + state.zones[`F${zone.floor}-C${i}`].fire, 0) / 5
        : zone.fire;
      assert(zone.smoke <= localFire + cap + 1e-9, `${zone.id} smoke cap`);
    }
    for (let floor = 2; floor <= 10; floor += 1) {
      const smoke = state.zones[`F${floor}-C1`].smoke;
      for (let i = 2; i <= 5; i += 1) assert.equal(state.zones[`F${floor}-C${i}`].smoke, smoke);
    }
    previousFire = Object.fromEntries(Object.values(state.zones).map((z) => [z.id, z.fire]));
  }
  assert(state.ended, "scenario reaches its defined terminal state");
  assert(Object.values(state.zones).every((z) => z.fire === 100));
  assert(Object.values(state.zones).filter((z) => z.collapsed).length <= 2);
  assert.equal(stepSimulation(state), state, "finished scenario remains fixed");
}

function testOpenRoofSmokeCapAcrossWinds() {
  let sawSmokeAboveRoofCapElsewhere = false;
  let roofReachedCap = false;
  for (const wind of [1, 5, 10, 15]) {
    let state = createSimulation({ seed: 2026, wind, ignitionId: "F10-R9" });
    while (!state.ended && state.second < 30 * 60) {
      state = stepSimulation(state);
      const roofSmoke = state.zones["F11-ROOF"].smoke;
      assert(roofSmoke >= 0 && roofSmoke <= roofCap + 1e-9,
             `roof smoke exceeded ${roofCap} at ${wind} m/s, second ${state.second}`);
      roofReachedCap ||= roofSmoke >= roofCap - 1e-9;
      sawSmokeAboveRoofCapElsewhere ||= state.zones["F10-SA"].smoke > roofCap;
    }
  }
  assert(roofReachedCap, "the roof cap becomes active during the scenario");
  assert(sawSmokeAboveRoofCapElsewhere, "the roof cap does not clamp the stairwell");

  let legacy = createSimulation({ seed: 2026, wind: 15, ignitionId: "F10-R9",
    roofSmokeCap: 100 });
  let legacyExceedsNewCap = false;
  while (!legacy.ended && legacy.second < 30 * 60) {
    legacy = stepSimulation(legacy);
    legacyExceedsNewCap ||= legacy.zones["F11-ROOF"].smoke > roofCap;
  }
  assert(legacyExceedsNewCap, "saved models can retain their earlier roof smoke rule");
}

function testSecondsPreserveMinuteRate() {
  let state = createSimulation({ seed: 2026, wind: 5 });
  const ignitionGrowth = globalThis.FireEvacConfig.FIRE_GROWTH_PER_MINUTE * fireGrowthMultiplier(18);
  for (let second = 1; second <= 60; second += 1) {
    state = stepSimulation(state);
    assert.equal(state.second, second);
    if (second === 30) {
      assert(Math.abs(state.zones[state.ignitionId].fire - (18 + ignitionGrowth / 2)) < 1e-9);
      assert.equal(state.minute, 0);
    }
  }
  assert.equal(state.minute, 1);
  assert(Math.abs(state.zones[state.ignitionId].fire - (18 + ignitionGrowth)) < 1e-9);
  assert.equal(state.zones[state.ignitionId].smoke, 14.4);
  assert.equal(state.zones["F1-L"].fire, 0.576);
  assert.equal(state.zones["F1-L"].smoke, 12.6);
  assert(state.zones["F1-L"].smoke > state.zones["F1-L"].fire, "smoke reaches the lobby before significant fire");
}

function testFireGrowthAcceleration() {
  assert.equal(fireGrowthMultiplier(0), 1);
  assert.equal(fireGrowthMultiplier(35), 1.5);
  assert.equal(fireGrowthMultiplier(70), 2);
  assert.equal(fireGrowthMultiplier(100), 2);

  // New fire in a neighbor still uses the original spread coefficient.
  const state = createSimulation({ seed: 2026, wind: 5, ignitionId: "F2-R1" });
  let next = state;
  for (let second = 0; second < 60; second += 1) next = stepSimulation(next);
  assert.equal(next.zones["F2-C1"].fire, 18 * globalThis.FireEvacConfig.FIRE_SPREAD_PER_MINUTE);
  assert.equal(next.zones["F2-R1"].smoke, 18 * globalThis.FireEvacConfig.SMOKE_GENERATION_PER_FIRE);

  // A saved run can replay its original fire law after working defaults change.
  let legacy = createSimulation({ seed: 2026, wind: 5, ignitionId: "F2-R1",
    fireGrowthAcceleration: {fullAt: 70, maxMultiplier: 1} });
  for (let second = 0; second < 60; second += 1) legacy = stepSimulation(legacy);
  assert.equal(legacy.zones["F2-R1"].fire, 24.5);
  assert.equal(legacy.zones["F2-C1"].fire, next.zones["F2-C1"].fire);
  assert.equal(legacy.zones["F2-R1"].smoke, next.zones["F2-R1"].smoke);
}

function testRoomShelterOpportunity() {
  let state = createSimulation({ seed: 2026, wind: 5 });
  let legacy = createSimulation({ seed: 2026, wind: 5,
    fireGrowthAcceleration: {fullAt: 70, maxMultiplier: 1} });
  while (state.second < 25 * 60) state = stepSimulation(state);
  while (legacy.second < 25 * 60) legacy = stepSimulation(legacy);
  const rooms = Object.values(state.zones).filter((zone) => zone.type === "room");
  const viable = rooms.filter((zone) => zone.fire <= 50 && zone.smoke < 80 && !zone.collapsed);
  const legacyFireSafe = Object.values(legacy.zones).filter((zone) => zone.type === "room" && zone.fire <= 50);
  const newFireSafe = rooms.filter((zone) => zone.fire <= 50);
  assert(newFireSafe.length < legacyFireSafe.length, "accelerating existing fire reduces the 25-minute refuge count");
  assert(viable.length > 0, "some rooms remain viable at wind 5 in this scenario");
  assert(state.zones[state.ignitionId].fire > 50, "the ignition room is not a refuge");
}

function testReproducibility() {
  let first = createSimulation({ seed: 2026, wind: 5 });
  let second = createSimulation({ seed: 2026, wind: 5 });
  for (let i = 0; i < 20; i += 1) {
    first = stepSimulation(first);
    second = stepSimulation(second);
  }
  assert.deepEqual(first, second);
}

function testManualIgnitionRoom() {
  const options = { seed: 2026, wind: 5, ignitionId: "F10-R9" };
  const first = createSimulation(options);
  const second = createSimulation(options);
  assert.equal(first.ignitionId, "F10-R9");
  assert.equal(first.zones["F10-R9"].fire, globalThis.FireEvacConfig.INITIAL_FIRE);
  assert.equal(first.events[0].zoneId, "F10-R9");
  assert.deepEqual(stepSimulation(first), stepSimulation(second));
  assert.equal(createSimulation({ seed: 2026, wind: 5, ignitionId: "" }).ignitionId,
               createSimulation({ seed: 2026, wind: 5 }).ignitionId);
  assert.throws(() => createSimulation({ ...options, ignitionId: "F10-C1" }), RangeError);
  assert.throws(() => createSimulation({ ...options, ignitionId: "F11-ROOF" }), RangeError);
}

testTopologyAndDirection();
testSmokeCapAndCompletion();
testOpenRoofSmokeCapAcrossWinds();
testSecondsPreserveMinuteRate();
testFireGrowthAcceleration();
testRoomShelterOpportunity();
testReproducibility();
testManualIgnitionRoom();
console.log("Engine checks passed.");
