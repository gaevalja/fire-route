/* Run the final PPO actor and the existing fire engine directly in a browser. */
(function (global) {
  "use strict";

  const engine = global.FireEvacEngine;
  if (!engine) throw new Error("config.js and engine.js must load before offline_replay.js");
  const DEATH_FIRE = 60;
  const DEATH_SMOKE = 80;
  const WAIT = 162;
  const EXIT = 163;
  const LEGACY_RESCUE_RULES = Object.freeze({
    roofAtSecond: 1200, roomAtSecond: 1500, roomFireMax: 50
  });
  const LEGACY_FIRE_GROWTH = Object.freeze({fullAt: 70, maxMultiplier: 1});

  function fireGrowthRule(policy) {
    const rule = policy && policy.fireGrowthAcceleration != null
      ? policy.fireGrowthAcceleration : LEGACY_FIRE_GROWTH;
    if (!rule || typeof rule !== "object" ||
        !Number.isFinite(rule.fullAt) || rule.fullAt <= 0 ||
        !Number.isFinite(rule.maxMultiplier) || rule.maxMultiplier < 1) {
      throw new Error("모델의 불 증가 규칙이 올바르지 않습니다.");
    }
    return rule;
  }

  function isRoom(id) { return /^F\d+-R\d+$/.test(id); }

  function deathPenalty(policy, decisionIndex) {
    const base = policy.deathReward == null ? -100 : policy.deathReward;
    return policy.rewardScheme === "discount_neutral_death_v2"
      ? base / Math.pow(policy.rewardGamma, decisionIndex)
      : base;
  }
  function elevatorDeathPenalty(policy, decisionIndex) {
    const base = policy.terminalRewards == null
      ? (policy.deathReward == null ? -100 : policy.deathReward)
      : policy.terminalRewards.elevatorDeath;
    return policy.rewardScheme === "discount_neutral_death_v2"
      ? base / Math.pow(policy.rewardGamma, decisionIndex)
      : base;
  }
  function terminalReward(policy, kind) {
    if (policy.terminalRewards == null) {
      return {exit: 100, roof: 70, room: 40}[kind];
    }
    return policy.terminalRewards[kind];
  }
  function secondCost(policy, fire, smoke) {
    const costs = policy.rewardCosts;
    if (costs == null) return 0.005 + 0.02 * fire / 100 + 0.01 * smoke / 100;
    const fireRisk = Math.max(0, fire - costs.fireHighRiskStart) /
      Math.max(1, costs.fireDeathAt - costs.fireHighRiskStart);
    const smokeRisk = Math.max(0, smoke - costs.smokeHighRiskStart) /
      Math.max(1, costs.smokeDeathAt - costs.smokeHighRiskStart);
    return costs.timePerSecond + costs.fireLinearPerSecond * fire / 100 +
      costs.smokeLinearPerSecond * smoke / 100 +
      costs.fireHighRiskPerSecond * fireRisk * fireRisk +
      costs.smokeHighRiskPerSecond * smokeRisk * smokeRisk;
  }
  function validatePolicy(policy, zoneIds) {
    if (!policy || policy.schema !== "fire-evac-browser-policy-v1") throw new Error("지원하지 않는 모델 파일입니다.");
    if (policy.featureSet !== "full_hazard_v1") throw new Error("이 화면에서 아직 지원하지 않는 관찰 형식입니다.");
    if (policy.observationDim !== 649 || policy.actionCount !== 164 || policy.activation !== "relu") {
      throw new Error("모델의 입력·행동 크기 또는 활성 함수가 다릅니다.");
    }
    if (!Array.isArray(policy.zoneIds) || policy.zoneIds.length !== zoneIds.length ||
        policy.zoneIds.some((id, i) => id !== zoneIds[i])) {
      throw new Error("모델의 구역 순서가 현재 건물과 다릅니다.");
    }
    const scheme = policy.rewardScheme || "legacy_v1";
    if (!["legacy_v1", "discount_neutral_death_v2"].includes(scheme) ||
        (policy.deathReward != null && (!Number.isFinite(policy.deathReward) || policy.deathReward >= 0)) ||
        (policy.awarenessSeconds != null &&
         (!Number.isSafeInteger(policy.awarenessSeconds) || policy.awarenessSeconds < 0)) ||
        (scheme === "discount_neutral_death_v2" &&
         (!Number.isFinite(policy.rewardGamma) || policy.rewardGamma <= 0 || policy.rewardGamma > 1))) {
      throw new Error("모델의 보상 규칙이 올바르지 않습니다.");
    }
    const actionSeconds = policy.actionSeconds == null ? 30 : policy.actionSeconds;
    if (!Number.isSafeInteger(actionSeconds) || actionSeconds <= 0) {
      throw new Error("모델의 기본 행동 시간이 올바르지 않습니다.");
    }
    if (policy.terminalRewards != null) {
      const rewards = policy.terminalRewards;
      if (typeof rewards !== "object" || rewards === null ||
          !["exit", "roof", "room", "elevatorDeath"].every((key) => Number.isFinite(rewards[key])) ||
          rewards.elevatorDeath >= 0) {
        throw new Error("모델의 구조 보상이 올바르지 않습니다.");
      }
    }
    if (policy.rewardCosts != null) {
      const costs = policy.rewardCosts;
      const nonnegative = ["timePerSecond", "fireLinearPerSecond", "smokeLinearPerSecond",
        "fireHighRiskPerSecond", "smokeHighRiskPerSecond"];
      const thresholds = ["fireHighRiskStart", "smokeHighRiskStart", "fireDeathAt", "smokeDeathAt"];
      if (typeof costs !== "object" || costs === null ||
          !nonnegative.every((key) => Number.isFinite(costs[key]) && costs[key] >= 0) ||
          !thresholds.every((key) => Number.isFinite(costs[key]) && costs[key] >= 0 && costs[key] <= 100) ||
          costs.fireDeathAt <= 0 || costs.smokeDeathAt <= 0) {
        throw new Error("모델의 위험 비용 규칙이 올바르지 않습니다.");
      }
    }
    if (policy.roofSmokeCap != null &&
        (!Number.isFinite(policy.roofSmokeCap) || policy.roofSmokeCap < 0 || policy.roofSmokeCap > 100)) {
      throw new Error("모델의 옥상 연기 상한이 올바르지 않습니다.");
    }
    if (policy.rescueRules != null) {
      const rules = policy.rescueRules;
      if (typeof rules !== "object" || rules === null ||
          !Number.isSafeInteger(rules.roofAtSecond) || rules.roofAtSecond < 0 ||
          !Number.isSafeInteger(rules.roomAtSecond) || rules.roomAtSecond < 0 ||
          !Number.isFinite(rules.roomFireMax) || rules.roomFireMax < 0 || rules.roomFireMax > 100) {
        throw new Error("모델의 구조 시각 또는 방 구조 기준이 올바르지 않습니다.");
      }
    }
    if (policy.slowMove != null) {
      const rule = policy.slowMove;
      if (!rule || typeof rule !== "object" ||
          !Number.isFinite(rule.fireAbove) || rule.fireAbove < 0 || rule.fireAbove > 100 ||
          !Number.isFinite(rule.smokeAbove) || rule.smokeAbove < 0 || rule.smokeAbove > 100 ||
          !Number.isSafeInteger(rule.seconds) || rule.seconds < actionSeconds) {
        throw new Error("모델의 위험 구역 이동 시간이 올바르지 않습니다.");
      }
    }
    fireGrowthRule(policy);
    const dimensions = [[128, 649], [128, 128], [164, 128]];
    if (!Array.isArray(policy.layers) || policy.layers.length !== 3) throw new Error("모델의 계층 정보가 없습니다.");
    policy.layers.forEach((layer, index) => {
      const [rows, columns] = dimensions[index];
      if (!Array.isArray(layer.weight) || layer.weight.length !== rows ||
          !Array.isArray(layer.bias) || layer.bias.length !== rows ||
          layer.weight.some((row) => !Array.isArray(row) || row.length !== columns)) {
        throw new Error("모델 계층 크기가 예상과 다릅니다.");
      }
    });
  }

  function pickStartRoom(seed, roomIds) {
    const index = Number((BigInt(seed) * 2654435761n + 1013904223n) % BigInt(roomIds.length));
    return roomIds[index];
  }

  function observation(state, position, zoneIds) {
    const values = new Float32Array(649);
    zoneIds.forEach((id, index) => {
      const zone = state.zones[id];
      const offset = index * 4;
      values[offset] = zone.fire / 100;
      values[offset + 1] = zone.smoke / 100;
      values[offset + 2] = zone.collapsed ? 1 : 0;
      values[offset + 3] = id === position ? 1 : 0;
    });
    values[648] = Math.min(state.second / 1500, 1);
    return values;
  }

  function linear(layer, input, relu) {
    const output = new Float32Array(layer.bias.length);
    for (let row = 0; row < layer.bias.length; row += 1) {
      let total = layer.bias[row];
      const weights = layer.weight[row];
      for (let column = 0; column < input.length; column += 1) total += weights[column] * input[column];
      output[row] = relu ? Math.max(0, total) : total;
    }
    return output;
  }

  function actionMask(state, position, zoneIds) {
    const mask = new Array(164).fill(false);
    mask[WAIT] = true;
    const index = new Map(zoneIds.map((id, i) => [id, i]));
    for (const id of engine.getMovementNeighbors(position)) {
      if (!state.zones[id].collapsed) mask[index.get(id)] = true;
    }
    if (position === "F1-L") mask[EXIT] = true;
    return mask;
  }

  function chooseAction(policy, input, mask) {
    const hidden1 = linear(policy.layers[0], input, true);
    const hidden2 = linear(policy.layers[1], hidden1, true);
    const logits = linear(policy.layers[2], hidden2, false);
    let best = -1;
    let bestValue = -Infinity;
    for (let index = 0; index < logits.length; index += 1) {
      if (mask[index] && (best < 0 || logits[index] > bestValue)) {
        best = index;
        bestValue = logits[index];
      }
    }
    if (best < 0) throw new Error("선택할 수 있는 행동이 없습니다.");
    return best;
  }

  function deathReason(state, position, policy) {
    const zone = state.zones[position];
    if (zone.collapsed) return "collapse";
    const fireLimit = policy.rewardCosts == null ? DEATH_FIRE : policy.rewardCosts.fireDeathAt;
    const smokeLimit = policy.rewardCosts == null ? DEATH_SMOKE : policy.rewardCosts.smokeDeathAt;
    if (zone.fire >= fireLimit) return "fire";
    if (zone.smoke >= smokeLimit) return "smoke";
    return null;
  }

  function movementDuration(policy, state, origin, destination, action) {
    const normal = policy.actionSeconds == null ? 30 : policy.actionSeconds;
    const rule = policy.slowMove;
    if (action === WAIT || rule == null) return normal;
    const originZone = state.zones[origin];
    const destinationZone = state.zones[destination];
    return [originZone, destinationZone].some((zone) => zone &&
      (zone.fire > rule.fireAbove || zone.smoke > rule.smokeAbove)) ? rule.seconds : normal;
  }

  function copyFrame(state, position) {
    const zones = {};
    for (const [id, zone] of Object.entries(state.zones)) {
      zones[id] = { fire: Math.round(zone.fire * 1000) / 1000,
                    smoke: Math.round(zone.smoke * 1000) / 1000,
                    collapsed: Boolean(zone.collapsed) };
    }
    return { second: state.second, zones, agentZone: position };
  }

  function actionLabel(action, target) {
    if (action === WAIT) return "현재 구역에서 대기";
    if (action === EXIT) return "1층 출입구로 이동";
    if (target.endsWith("-E")) return "엘리베이터 선택";
    return `${target} 구역으로 이동`;
  }

  function generateReplay(policy, options) {
    const wind = Number(options.wind);
    const seed = Number(options.seed);
    if (![1, 5, 10, 15].includes(wind)) throw new Error("풍속은 1·5·10·15 m/s 중 하나여야 합니다.");
    if (!Number.isSafeInteger(seed) || seed < 1 || seed > 4294967295) throw new Error("시나리오 번호가 올바르지 않습니다.");
    let state = engine.createSimulation({
      seed, wind, ignitionId: options.ignitionId || undefined,
      fireGrowthAcceleration: fireGrowthRule(policy),
      roofSmokeCap: policy.roofSmokeCap == null ? 100 : policy.roofSmokeCap,
    });
    const zoneIds = Object.keys(state.zones);
    validatePolicy(policy, zoneIds);
    const rescueRules = policy.rescueRules == null ? LEGACY_RESCUE_RULES : policy.rescueRules;
    const awarenessSeconds = policy.awarenessSeconds == null ? 60 : policy.awarenessSeconds;
    const rooms = zoneIds.filter(isRoom);
    const startRoom = options.startRoom || pickStartRoom(seed, rooms);
    if (!rooms.includes(startRoom)) throw new Error("시작 위치는 방이어야 합니다.");
    let position = startRoom;
    let outcome = null;
    let reason = null;
    let totalReward = 0;
    const frames = [copyFrame(state, position)];

    function finish(kind, why, eventText) {
      outcome = kind;
      reason = why || null;
      const frame = copyFrame(state, position);
      frame.event = eventText;
      frames.push(frame);
    }
    function recordIfNeeded() {
      if (state.second % 30 === 0) frames.push(copyFrame(state, position));
    }

    // No observation or decisions are given to the actor before awareness.
    for (let second = 1; second <= awarenessSeconds; second += 1) {
      state = engine.stepSimulation(state);
      const danger = deathReason(state, position, policy);
      if (danger) {
        totalReward = deathPenalty(policy, 0);
        finish("death", danger, "화재를 알아차리기 전 사망");
        break;
      }
      recordIfNeeded();
    }

    for (let decisions = 0; !outcome && decisions < 10000; decisions += 1) {
      const mask = actionMask(state, position, zoneIds);
      const action = chooseAction(policy, observation(state, position, zoneIds), mask);
      const origin = position;
      const destination = action < zoneIds.length ? zoneIds[action] : action === EXIT ? "EXIT" : position;
      const durationSeconds = movementDuration(policy, state, origin, destination, action);
      const label = actionLabel(action, destination) +
        (action !== WAIT && durationSeconds > (policy.actionSeconds == null ? 30 : policy.actionSeconds)
          ? ` (${durationSeconds}초)` : "");
      let reward = 0;
      if (action < zoneIds.length) position = destination;

      function annotate(frame) {
        frame.action = {label, from: origin, to: destination, durationSeconds};
        frame.reward = Math.round(reward * 10000) / 10000;
      }

      if (position.endsWith("-E") && action < zoneIds.length) {
        reward = elevatorDeathPenalty(policy, decisions);
        totalReward += reward;
        finish("death", "elevator", "엘리베이터 선택으로 사망");
        annotate(frames[frames.length - 1]);
        break;
      }
      const immediateDanger = deathReason(state, position, policy);
      if (immediateDanger) {
        reward = deathPenalty(policy, decisions);
        totalReward += reward;
        finish("death", immediateDanger, "위험 구역에 들어가 사망");
        annotate(frames[frames.length - 1]);
        break;
      }

      for (let elapsed = 1; elapsed <= durationSeconds; elapsed += 1) {
        state = engine.stepSimulation(state);
        const zone = state.zones[position];
        reward -= secondCost(policy, zone.fire, zone.smoke);
        const danger = deathReason(state, position, policy);
        if (danger) {
          reward += deathPenalty(policy, decisions);
          finish("death", danger, "위험 수치 또는 붕괴로 사망");
          break;
        }
        if (elapsed === durationSeconds) {
          if (action === EXIT) {
            position = "EXIT";
            reward += terminalReward(policy, "exit");
            finish("exit", null, "1층 출입구에서 구조");
            break;
          }
          if (position === "F11-ROOF" && state.second >= rescueRules.roofAtSecond) {
            reward += terminalReward(policy, "roof");
            finish("roof", null, "옥상에서 구조");
            break;
          }
          if (state.second >= rescueRules.roomAtSecond && isRoom(position) &&
              zone.fire <= rescueRules.roomFireMax) {
            reward += terminalReward(policy, "room");
            finish("room", null, "방에서 구조");
            break;
          }
        }
        if (state.ended) {
          reward += deathPenalty(policy, decisions);
          finish("death", "scenario_end", "모든 구역 화재 100으로 종료");
          break;
        }
        recordIfNeeded();
      }
      totalReward += reward;
      if (outcome) {
        annotate(frames[frames.length - 1]);
      } else {
        const last = frames[frames.length - 1];
        if (last.second !== state.second) frames.push(copyFrame(state, position));
        annotate(frames[frames.length - 1]);
      }
    }
    if (!outcome) throw new Error("재생이 10,000번의 행동 안에 종료되지 않았습니다.");
    return {
      run: policy.run, wind, seed, ignitionId: state.ignitionId,
      startRoom, outcome, deathReason: reason,
      totalReward: Math.round(totalReward * 10000) / 10000,
      frames
    };
  }

  global.FireEvacOffline = Object.freeze({
    validatePolicy, observation, actionMask, chooseAction,
    pickStartRoom, movementDuration, generateReplay
  });
})(typeof window !== "undefined" ? window : globalThis);
