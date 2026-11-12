/* Run with: node test_engine.js */
const assert = require("node:assert/strict");
require("./config.js");
require("./engine.js");

const { createSimulation, stepSimulation } = globalThis.FireEvacEngine;
const cap = globalThis.FireEvacConfig.SMOKE_ABOVE_FIRE_CAP;

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

function testSecondsPreserveMinuteRate() {
  let state = createSimulation({ seed: 2026, wind: 5 });
  for (let second = 1; second <= 60; second += 1) {
    state = stepSimulation(state);
    assert.equal(state.second, second);
    if (second === 30) {
      assert(Math.abs(state.zones[state.ignitionId].fire - 21.25) < 1e-9);
      assert.equal(state.minute, 0);
    }
  }
  assert.equal(state.minute, 1);
  assert.equal(state.zones[state.ignitionId].fire, 24.5);
  assert.equal(state.zones[state.ignitionId].smoke, 14.4);
  assert.equal(state.zones["F1-L"].fire, 0.576);
  assert.equal(state.zones["F1-L"].smoke, 12.6);
  assert(state.zones["F1-L"].smoke > state.zones["F1-L"].fire, "smoke reaches the lobby before significant fire");
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

testTopologyAndDirection();
testSmokeCapAndCompletion();
testSecondsPreserveMinuteRate();
testReproducibility();
console.log("Engine checks passed.");
