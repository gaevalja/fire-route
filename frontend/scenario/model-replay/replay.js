(() => {
  "use strict";

  const locale = globalThis.FireRouteLocale;
  const {t, getLanguage} = locale;
  locale.localize(document);
  const byId = (id) => document.getElementById(id);
  const el = {
    notice: byId("notice"), run: byId("run-select"), modelCaption: byId("model-caption"),
    mode: byId("replay-mode"), followPolicy: byId("follow-policy"), rules: byId("comparison-rules"),
    refresh: byId("refresh-button"), offlineImport: byId("offline-import"),
    folderInput: byId("run-folder-input"), policyInput: byId("policy-file-input"),
    wind: byId("wind-select"), seed: byId("seed-input"),
    ignitionSelect: byId("ignition-select"), start: byId("start-select"),
    generate: byId("generate-button"), back: byId("back-button"), play: byId("play-button"),
    next: byId("next-button"), speed: byId("speed-select"), follow: byId("follow-agent"),
    jumpAgent: byId("jump-agent"), floorTitle: byId("floor-title"), floorTabs: byId("floor-tabs"),
    floorplan: byId("floorplan"), range: byId("timeline-range"),
    timelineCurrent: byId("timeline-current"), timelineEnd: byId("timeline-end"),
    time: byId("time-value"), timeTotal: byId("time-total"), agent: byId("agent-value"),
    startValue: byId("start-value"), ignition: byId("ignition-value"),
    windValue: byId("wind-value"), outcome: byId("outcome-value"),
    outcomeDetail: byId("outcome-detail"), action: byId("action-value"),
    risk: byId("risk-value"), reward: byId("reward-value"),
    selected: byId("selected-value"), selectedDetail: byId("selected-detail"),
    events: byId("event-list"), lossSelect: byId("loss-select"),
    lossChart: byId("loss-chart"), lossReadout: byId("loss-readout"),
    evalReadout: byId("eval-readout")
  };

  const zoneIds = [];
  for (let floor = 1; floor <= 10; floor += 1) {
    for (let room = 1; room <= (floor === 1 ? 4 : 9); room += 1) zoneIds.push("F" + floor + "-R" + room);
    if (floor === 1) zoneIds.push("F1-L");
    else for (let corridor = 1; corridor <= 5; corridor += 1) zoneIds.push("F" + floor + "-C" + corridor);
    zoneIds.push("F" + floor + "-SA", "F" + floor + "-SB", "F" + floor + "-E");
  }
  zoneIds.push("F11-ROOF");

  const state = {
    runs: [], replay: null, metrics: null, floor: 2, frameIndex: 0,
    selectedZone: null, timer: null, events: [], requestId: 0,
    offlineModels: new Map(), hostedRuns: [], catalogLoading: false,
    generating: false, generation: 0
  };
  const offlineMode = location.protocol === "file:";
  const runsUrl = "./runs";
  const policies = {dijkstra: {get name() { return t("다익스트라", "Dijkstra"); }, marker: "D"}, ppo: {name: "PPO", marker: "P"}};
  const policyEntries = Object.entries(policies);
  const comparisonMode = () => !offlineMode && el.mode.value === "compare";

  function setNotice(message, kind) {
    el.notice.textContent = message;
    el.notice.className = "notice" + (kind ? " " + kind : "");
  }

  async function getJSON(url, options) {
    let response;
    try { response = await fetch(url, {cache: "no-store", ...options}); }
    catch { throw new Error(t("시연 서버에 연결할 수 없습니다.", "Cannot connect to the demo server.")); }
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error(t("서버 응답을 읽지 못했습니다.", "Cannot read the server response.")); }
    if (!response.ok) throw new Error(sourceText(data.error || data.message) || t("요청을 처리하지 못했습니다.", "The request could not be completed."));
    return data;
  }

  function selectedRun() {
    return state.runs.find((run) => run.id === el.run.value);
  }

  function isTraining(run) {
    return run?.status === "training" || run?.status === "running";
  }

  function updateGenerateButton() {
    const run = selectedRun();
    el.generate.disabled = state.generating || (!comparisonMode() && (!run?.has_model || isTraining(run)));
  }

  function clock(seconds) {
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    return String(Math.floor(value / 60)).padStart(2, "0") + ":" + String(value % 60).padStart(2, "0");
  }

  function number(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return "—";
    return parsed.toFixed(1);
  }

  function floorOf(zoneId) {
    const match = /^F(\d+)-/.exec(String(zoneId || ""));
    return match ? Number(match[1]) : null;
  }

  function zoneName(zoneId) {
    if (!zoneId) return "—";
    if (zoneId === "EXIT" || zoneId === "OUTSIDE") return t("1층 출입구", "Ground-floor exit");
    const match = /^F(\d+)-(R|C|S|E|L|ROOF)(\d+|[AB])?$/.exec(String(zoneId));
    if (!match) return String(zoneId);
    const floor = Number(match[1]);
    const type = match[2], suffix = match[3] || "";
    if (type === "R") return t(`${floor}층 방 ${suffix}`, `Floor ${floor}, room ${suffix}`);
    if (type === "C") return t(`${floor}층 복도 ${suffix}`, `Floor ${floor}, corridor ${suffix}`);
    if (type === "S") return t(`${floor}층 비상계단 ${suffix}`, `Floor ${floor}, stairs ${suffix}`);
    if (type === "E") return t(`${floor}층 엘리베이터`, `Floor ${floor}, elevator`);
    if (type === "L") return t("1층 로비", "Ground-floor lobby");
    return t("11층 옥상", "Roof (floor 11)");
  }

  // Historical PPO outputs carry Korean labels. Keep the archived replay data intact.
  const sourceEnglish = new Map(Object.entries({
    AUTH_REQUIRED: "Sign in to continue.", ROLE_DENIED: "This action requires responder access.",
    "현재 구역에서 대기": "Wait in the current zone",
    "1층 출입구로 이동": "Move to the ground-floor exit",
    "엘리베이터 선택": "Choose the elevator",
    "화재를 알아차리기 전 사망": "Died before becoming aware of the fire",
    "엘리베이터 선택으로 사망": "Died after choosing the elevator",
    "위험 구역에 들어가 사망": "Died on entering a hazardous zone",
    "위험 수치 또는 붕괴로 사망": "Died due to hazards or collapse",
    "1층 출입구에서 구조": "Rescued at the ground-floor exit",
    "옥상에서 구조": "Rescued on the roof",
    "방에서 구조": "Rescued in a room",
    "모든 구역 화재 100으로 종료": "The fire index reached 100 in every zone",
    "건물 전체 위험도 · 시간 · 현재 위치": "Building-wide hazards · time · current position",
    "시나리오 입력 항목을 확인해 주세요.": "Check the scenario inputs.",
    "시나리오 번호는 1부터 4,294,967,295까지의 정수여야 합니다.": "Enter an integer seed from 1 to 4,294,967,295.",
    "풍속은 1·5·10·15 m/s 중 하나여야 합니다.": "Choose a wind speed of 1, 5, 10 or 15 m/s.",
    "시작 위치와 발화 위치는 건물의 방이어야 합니다.": "Choose building rooms for the start and ignition locations.",
    "비교 모델을 불러올 수 없습니다.": "Cannot load the comparison model.",
    "모델의 불 증가 규칙이 올바르지 않습니다.": "The model's fire growth rules are invalid.",
    "지원하지 않는 모델 파일입니다.": "This model file is unsupported.",
    "이 화면에서 아직 지원하지 않는 관찰 형식입니다.": "This viewer does not support the model's observation format.",
    "모델의 입력·행동 크기 또는 활성 함수가 다릅니다.": "The model dimensions or activation function do not match the viewer.",
    "모델의 구역 순서가 현재 건물과 다릅니다.": "The model's zone order does not match the building.",
    "모델의 보상 규칙이 올바르지 않습니다.": "The model's reward rules are invalid.",
    "모델의 기본 행동 시간이 올바르지 않습니다.": "The model's default action time is invalid.",
    "모델의 구조 보상이 올바르지 않습니다.": "The model's rescue rewards are invalid.",
    "모델의 위험 비용 규칙이 올바르지 않습니다.": "The model's hazard cost rules are invalid.",
    "모델의 옥상 연기 상한이 올바르지 않습니다.": "The model's roof smoke cap is invalid.",
    "모델의 구조 시각 또는 방 구조 기준이 올바르지 않습니다.": "The model's rescue time or room rescue rules are invalid.",
    "모델의 위험 구역 이동 시간이 올바르지 않습니다.": "The model's travel time in hazardous zones is invalid.",
    "모델의 계층 정보가 없습니다.": "The model's network layers are missing.",
    "모델 계층 크기가 예상과 다릅니다.": "The model's network dimensions do not match the viewer.",
    "선택할 수 있는 행동이 없습니다.": "No action is available.",
    "시나리오 번호가 올바르지 않습니다.": "The scenario seed is invalid.",
    "시작 위치는 방이어야 합니다.": "Choose a room as the starting location.",
    "재생이 10,000번의 행동 안에 종료되지 않았습니다.": "The replay did not finish within 10,000 actions."
  }));

  function sourceText(value) {
    const errors = {AUTH_REQUIRED: "다시 로그인해 주세요.", ROLE_DENIED: "구조대 권한이 필요합니다."};
    return t(errors[value] ?? value, sourceEnglish.get(value) ?? value);
  }

  function moveLabel(zone) { return t(`${zoneName(zone)}로 이동`, `Move to ${zoneName(zone)}`); }

  function actionName(action) {
    if (action == null || action === "") return "—";
    if (typeof action === "string") {
      if (action === "WAIT") return t("현재 위치에서 대기", "Wait in place");
      if (action === "EXIT") return sourceText("1층 출입구로 이동");
      if (/^F\d+-/.test(action)) return moveLabel(action);
      return sourceText(action);
    }
    if (typeof action === "number") {
      if (action === 162) return actionName("WAIT");
      if (action === 163) return actionName("EXIT");
      return zoneIds[action] ? moveLabel(zoneIds[action]) : t("행동 " + action, "Action " + action);
    }
    if (typeof action === "object") {
      if (action.label && getLanguage() === "ko") return String(action.label);
      if (action.type === "wait") return actionName("WAIT");
      if (action.type === "exit") return actionName("EXIT");
      const target = action.to || action.destination || action.zoneId;
      if (target) {
        const label = target === action.from ? actionName("WAIT")
          : target.endsWith("-E") ? sourceText("엘리베이터 선택") : moveLabel(target);
        return action.durationSeconds ? t(`${label} · ${action.durationSeconds}초`,`${label} · ${action.durationSeconds} s`) : label;
      }
      if (action.label) return sourceText(String(action.label));
    }
    return String(action);
  }

  function outcomeName(outcome) {
    const value = typeof outcome === "object" && outcome !== null
      ? (outcome.type || outcome.result || outcome.reason || "")
      : String(outcome || "");
    const names = {
      exit: ["출입구 구조", "Rescued at exit"], roof: ["옥상 구조", "Rescued on roof"],
      room: ["방 구조", "Rescued in room"], death: ["사망", "Died"], dead: ["사망", "Died"],
      elevator: ["엘리베이터 사망", "Died in elevator"], timeout: ["시나리오 종료", "Scenario ended"],
      unfinished: ["종료 전 생존", "Survived until end"], incomplete: ["시간 한도까지 미종료", "Unfinished at time limit"]
    };
    const label = names[String(value).toLowerCase()];
    return label ? t(...label) : value || "—";
  }

  function fillRoomSelect(select) {
    for (let floor = 1; floor <= 10; floor += 1) {
      for (let room = 1; room <= (floor === 1 ? 4 : 9); room += 1) {
        const option = document.createElement("option");
        option.value = "F" + floor + "-R" + room;
        option.textContent = zoneName(option.value);
        select.append(option);
      }
    }
  }

  function clearReplay() {
    pause();
    state.generation += 1;
    state.replay = null;
    state.frameIndex = 0;
    state.selectedZone = null;
    state.events = [];
    render();
  }

  function offlineRunRecord(policy) {
    const movement = policy.slowMove
      ? t(`위험 구역 이동 ${policy.slowMove.seconds}초`,`Hazardous-zone travel ${policy.slowMove.seconds} s`)
      : t(`이동 ${policy.actionSeconds ?? 30}초`,`Travel ${policy.actionSeconds ?? 30} s`);
    return {
      id: String(policy.run), status: "complete", has_model: true,
      training_wind: policy.trainingWind,
      awareness_seconds: policy.awarenessSeconds == null ? 60 : policy.awarenessSeconds,
      description: movement + t(" · 브라우저에서 직접 재생", " · Browser replay")
    };
  }

  async function importOfflineFiles(fileList, replaceExisting) {
    const files = Array.from(fileList || []);
    const policies = files.filter((file) => file.name === "browser_policy.json");
    if (!policies.length) {
      throw new Error(t("선택한 항목에서 browser_policy.json을 찾지 못했습니다. 최신 모델 내보내기가 필요합니다.", "No browser_policy.json was found in the selection. Export the model for browser playback."));
    }
    const imported = new Map();
    const referenceZones = Object.keys(window.FireEvacEngine.createSimulation({seed: 2026, wind: 5}).zones);
    for (const file of policies) {
      const policy = JSON.parse(await file.text());
      window.FireEvacOffline.validatePolicy(policy, referenceZones);
      if (!/^FIRE_EVAC_\d{4,}$/.test(String(policy.run || ""))) throw new Error(t("모델 번호가 올바르지 않습니다.", "The model run ID is invalid."));
      const relativePath = String(file.webkitRelativePath || "").replace(/\\/g, "/");
      const prefix = relativePath ? relativePath.slice(0, -file.name.length) : "";
      const sameFolder = (name) => files.find((candidate) =>
        candidate.name === name &&
        (prefix ? String(candidate.webkitRelativePath || "").replace(/\\/g, "/") === prefix + name : false));
      imported.set(policy.run, {
        policy,
        progress: sameFolder("progress.csv"),
        evaluation: sameFolder("eval_progress.csv")
      });
    }
    if (replaceExisting) state.offlineModels.clear();
    for (const [id, model] of imported) state.offlineModels.set(id, model);
    const selection = imported.has(el.run.value) ? el.run.value : imported.keys().next().value;
    await showRuns(selection, {modelChanged: true});
  }

  function parseOfflineMetrics(progressText, evaluationText) {
    const metrics = {steps: [], policy_loss: [], value_loss: [], entropy: [], total_loss: [], eval_success: []};
    function rows(text) {
      if (!text) return [];
      const lines = text.replace(/^\uFEFF/, "").trim().split(/\r?\n/);
      const headers = (lines.shift() || "").split(",");
      return lines.map((line) => {
        const values = line.split(",");
        return Object.fromEntries(headers.map((header, i) => [header, values[i]]));
      });
    }
    const numeric = (value) => value?.trim() ? Number(value) : NaN;
    for (const row of rows(progressText)) {
      const step = numeric(row["time/total_timesteps"]);
      const policy = numeric(row["train/policy_gradient_loss"]);
      const value = numeric(row["train/value_loss"]);
      const entropy = numeric(row["train/entropy_loss"]);
      const total = numeric(row["train/loss"]);
      if (![step, policy, value, entropy, total].every(Number.isFinite)) continue;
      metrics.steps.push(step); metrics.policy_loss.push(policy); metrics.value_loss.push(value);
      metrics.entropy.push(-entropy); metrics.total_loss.push(total);
    }
    for (const row of rows(evaluationText)) {
      const success = numeric(row.success_rate);
      if (Number.isFinite(success)) metrics.eval_success.push(success);
    }
    return metrics;
  }

  async function showRuns(preferred = el.run.value, {modelChanged = false, refreshMetrics = true} = {}) {
    if (comparisonMode()) return;
    const prior = el.run.value;
    const models = new Map(state.hostedRuns.map((run) => [run.id, run]));
    for (const [id, model] of state.offlineModels) models.set(id, offlineRunRecord(model.policy));
    state.runs = [...models.values()];
    const options = state.runs.map((run) => {
      const status = isTraining(run) ? t(" · 학습 중", " · Training") : !run.has_model ? t(" · 최종 모델 없음", " · No final model") : "";
      return new Option(run.id + status, run.id);
    });
    el.run.replaceChildren(...(options.length ? options : [new Option(t("저장된 모델 없음", "No saved models"), "")]));
    if (models.has(preferred)) el.run.value = preferred;
    else if (models.has("FIRE_EVAC_0015")) el.run.value = "FIRE_EVAC_0015";
    if (prior !== el.run.value || modelChanged) clearReplay();
    if (refreshMetrics) { showSelection(); await loadMetrics(); }
    else updateRunCaption(selectedRun());
  }

  async function loadRuns() {
    if (offlineMode) return showRuns();
    if (state.catalogLoading) return;
    state.catalogLoading = true;
    el.refresh.disabled = true;
    try {
      const data = await getJSON(runsUrl);
      if (!Array.isArray(data.runs)) throw new Error(t("실행 목록 형식이 올바르지 않습니다.", "The training run list is invalid."));
      state.hostedRuns = data.runs;
      await showRuns();
    } catch (error) {
      if (!state.runs.length) el.run.replaceChildren(new Option(t("모델 목록을 읽지 못했습니다", "Cannot read the model list"), ""));
      updateGenerateButton();
      setNotice(t("모델 목록을 불러오지 못했습니다: ", "Cannot load the model list. ") + sourceText(error.message), "error");
    } finally {
      state.catalogLoading = false;
      el.refresh.disabled = false;
    }
  }

  function showSelection() {
    const run = selectedRun();
    updateGenerateButton();
    updateRunCaption(comparisonMode() ? null : run);
    if (state.generating) return;
    if (comparisonMode()) setNotice(t("공통 조건을 선택해 다익스트라와 PPO의 재생을 만드세요.", "Choose shared conditions to generate a Dijkstra and PPO replay."));
    else if (!run) setNotice(t("runs 폴더나 모델 파일을 선택해 주세요.", "Select a runs folder or a model file."));
    else if (isTraining(run)) setNotice(t("학습 중입니다. 손실 그래프를 5초마다 새로 고칩니다.", "Training in progress. The loss chart refreshes every five seconds."));
    else if (!run.has_model) setNotice(t("브라우저용 최종 모델이 아직 없습니다. 학습 기록은 확인할 수 있습니다.", "Training logs are available. Replay requires a final browser model."));
    else setNotice(t("테스트 풍속과 시나리오를 정해 재생을 만드세요.", "Choose a test wind speed and scenario to generate a replay."), "success");
  }

  function updateRunCaption(run) {
    for (const option of el.wind.options) {
      option.textContent = option.value + " m/s" + (Number(option.value) === run?.training_wind ? t(" · 학습 조건", " · Training wind") : "");
    }
    if (!run) { el.modelCaption.textContent = t("학습 중에는 손실을 보고, 완료 후 재생합니다.", "View training loss and replay after training."); return; }
    const pieces = [];
    if (run.created_at) {
      const date = new Date(run.created_at);
      pieces.push(t("시작 ", "Started ") + (Number.isNaN(date.getTime()) ? String(run.created_at) : date.toLocaleString(getLanguage())));
    }
    if (run.training_wind != null) pieces.push(t("학습 풍속 ", "Training wind ") + run.training_wind + " m/s");
    if (run.awareness_seconds != null) pieces.push(t("화재 인지 ", "Awareness delay ") + clock(run.awareness_seconds));
    if (isTraining(run)) pieces.push(t("학습 중 · 그래프 자동 새로 고침", "Training · chart refreshes automatically"));
    if (!run.has_model) pieces.push(t("최종 모델 없음", "No final model"));
    if (run.description) pieces.push(sourceText(String(run.description)));
    el.modelCaption.textContent = pieces.join(" · ") || t("최종 모델", "Final model");
  }

  async function readHostedMetrics(run, filename) {
    const response = await fetch(runsUrl + "/" + run + "/" + filename, {cache: "no-store"});
    if (response.status === 404) return "";
    if (!response.ok) throw new Error(t("학습 기록에 접근할 수 없습니다.", "Training logs are unavailable."));
    return response.text();
  }

  async function loadMetrics() {
    const run = el.run.value;
    const requestId = ++state.requestId;
    if (state.metricsRun !== run) {
      state.metrics = null;
      state.metricsFailed = false;
      drawChart();
    }
    state.metricsRun = run;
    if (!run) return;
    try {
      const local = state.offlineModels.get(run);
      const [progress, evaluation] = await Promise.all(local
        ? [local.progress?.text(), local.evaluation?.text()]
        : [readHostedMetrics(run, "progress.csv"), readHostedMetrics(run, "eval_progress.csv")]);
      if (requestId !== state.requestId) return;
      state.metrics = parseOfflineMetrics(progress, evaluation);
      state.metricsFailed = false;
      drawChart();
    } catch (error) {
      if (requestId !== state.requestId) return;
      state.metrics = null;
      state.metricsFailed = true;
      drawChart();
    }
  }

  function currentFrame() {
    const frames = state.replay && state.replay.frames;
    return frames && frames.length ? frames[state.frameIndex] : null;
  }

  function positionFloor(id) {
    return id === "EXIT" || id === "OUTSIDE" ? 1 : floorOf(id);
  }

  function agentFloor(frame) {
    if (!frame) return null;
    return positionFloor(frame.policies?.[el.followPolicy.value]?.position || frame.agentZone || frame.agent_zone || frame.position);
  }

  function extractEvents(frames) {
    const events = [];
    let lastAction = "";
    for (const frame of frames) {
      if (frame.action != null && frame.action !== "") {
        const label = actionName(frame.action);
        const key = String(frame.second) + "|" + label;
        if (key !== lastAction) events.push({second: frame.second, text: label});
        lastAction = key;
      }
      const list = Array.isArray(frame.event) ? frame.event : (frame.event ? [frame.event] : []);
      for (const event of list) {
        const text = typeof event === "object" && event !== null
          ? (event.message || event.label || event.type || JSON.stringify(event)) : String(event);
        if (text) events.push({second: frame.second, text: sourceText(text)});
      }
    }
    return events;
  }

  function decisionLabel(decision) {
    if (!decision) return t("화재 인지 전", "Awaiting fire awareness");
    if (!decision.route_available) return t(`출구 경로 없음 · ${decision.duration_seconds}초 대기`, `No exit route · wait ${decision.duration_seconds} s`);
    const label = decision.action === "move" ? moveLabel(decision.target)
      : actionName(decision.action.toUpperCase());
    return label + t(` · ${decision.duration_seconds}초`, ` · ${decision.duration_seconds} s`);
  }

  function trackOutcome(track) {
    const reasons = {fire: ["화재","Fire"], smoke: ["연기","Smoke"], collapse: ["붕괴","Collapse"],
      elevator: ["엘리베이터","Elevator"], scenario_end: ["시나리오 종료","Scenario ended"]};
    return outcomeName(track.outcome) + (track.finished_at == null ? "" : " · " + clock(track.finished_at))
      + (reasons[track.reason] ? " · " + t(...reasons[track.reason]) : "");
  }

  function comparisonEvents(replay) {
    const events = [];
    for (const [key, {name}] of policyEntries) {
      const track = replay.policies[key];
      for (const decision of track.decisions) events.push({second: decision.second, text: name + " · " + decisionLabel(decision)});
      if (track.finished_at != null) events.push({second: track.finished_at, text: name + " · " + trackOutcome(track)});
    }
    return events.sort((a, b) => a.second - b.second);
  }

  function showGenerating() {
    setNotice(comparisonMode() ? t("같은 화재에서 두 정책을 계산하는 중입니다.", "Running both policies against the same fire.")
      : t("모델을 적용해 시나리오를 계산하는 중입니다.", "Running the model on the selected scenario."));
  }

  function showReady(data) {
    const summary = data.policies ? t("시드 ", "Seed ") + data.seed + " · " + data.model_id : outcomeName(data.outcome);
    const count = data.frames.length;
    setNotice(t(`재생 준비 완료 · ${summary} · ${count}개 장면`, `Replay ready · ${summary} · ${count} frames`), "success");
  }

  async function generate() {
    if (state.generating) return;
    const compare = comparisonMode();
    const run = selectedRun();
    const wind = Number(el.wind.value);
    const seed = Number(el.seed.value);
    if (!compare && (!run?.has_model || isTraining(run))) return;
    if (!Number.isSafeInteger(seed) || seed < 1 || seed > 4294967295) {
      setNotice(t("시나리오 번호는 1부터 4,294,967,295까지의 정수로 입력해 주세요.", "Enter an integer seed from 1 to 4,294,967,295."), "error");
      return;
    }
    const options = {wind, seed, ignitionId: el.ignitionSelect.value || undefined,
                     startRoom: el.start.value || undefined};
    const generation = state.generation;
    pause();
    state.generating = true;
    updateGenerateButton();
    showGenerating();
    try {
      let data;
      if (compare) {
        data = await getJSON("./compare", {
          method: "POST", headers: {"Content-Type": "application/json"},
          body: JSON.stringify({seed, wind, ignition_room: options.ignitionId, start_room: options.startRoom})
        });
      } else {
        const local = state.offlineModels.get(run.id);
        const policy = local?.policy || await getJSON(`${runsUrl}/${run.id}/browser_policy.json`);
        await new Promise((resolve) => setTimeout(resolve, 0));
        if (generation !== state.generation) return;
        if (policy.run !== run.id) throw new Error(t("선택한 실행과 모델 파일의 번호가 다릅니다.", "The model file belongs to a different training run."));
        data = window.FireEvacOffline.generateReplay(policy, options);
      }
      if (generation !== state.generation) return;
      if (!Array.isArray(data.frames) || !data.frames.length) throw new Error(t("재생 장면이 비어 있습니다.", "The replay has no frames."));
      data.frames.sort((a, b) => Number(a.second) - Number(b.second));
      state.replay = data;
      state.frameIndex = 0;
      state.events = compare ? comparisonEvents(data) : extractEvents(data.frames);
      const first = currentFrame();
      state.floor = agentFloor(first) || 2;
      state.selectedZone = compare ? data.start_room : first?.agentZone || first?.agent_zone || null;
      render();
      showReady(data);
    } catch (error) {
      if (generation === state.generation) setNotice(t("재생을 만들지 못했습니다: ", "Cannot generate the replay. ") + sourceText(error.message), "error");
    } finally {
      state.generating = false;
      if (generation === state.generation) updateGenerateButton();
      else showSelection();
    }
  }

  function pause() {
    if (state.timer !== null) clearInterval(state.timer);
    state.timer = null;
    renderPlayLabel();
  }

  function renderPlayLabel() {
    el.play.textContent = state.timer === null ? t("▶ 재생", "▶ Play") : t("Ⅱ 일시 정지", "Ⅱ Pause");
  }

  function play() {
    if (!state.replay || state.replay.frames.length < 2) return;
    if (state.frameIndex >= state.replay.frames.length - 1) state.frameIndex = 0;
    const delay = Number(el.speed.value) || 550;
    state.timer = setInterval(() => {
      if (state.frameIndex >= state.replay.frames.length - 1) { pause(); return; }
      state.frameIndex += 1;
      render();
      if (state.frameIndex >= state.replay.frames.length - 1) pause();
    }, delay);
    renderPlayLabel();
    render();
  }

  function moveFrame(index) {
    const frames = state.replay && state.replay.frames;
    if (!frames) return;
    pause();
    state.frameIndex = Math.max(0, Math.min(frames.length - 1, index));
    render();
  }

  function tileColors(zone) {
    const fire = Math.max(0, Math.min(100, Number(zone.fire) || 0));
    const smoke = Math.max(0, Math.min(100, Number(zone.smoke) || 0));
    const f = (0.10 + fire / 140).toFixed(3);
    const s = (0.08 + smoke / 180).toFixed(3);
    const bg = "linear-gradient(150deg, rgba(241,105,65," + f + "), rgba(125,165,180," + s + ")), #20384d";
    const border = fire >= 60 ? "#ff9c70" : smoke >= 80 ? "#d0e0e4" : "#53778a";
    return {bg, border};
  }

  function makeTile(id, column, row, rowSpan, extraClass) {
    const frame = currentFrame();
    const zones = frame && frame.zones ? frame.zones : {};
    const zone = zones[id] || {fire: 0, smoke: 0, collapsed: false};
    const present = frame?.policies ? policyEntries.filter(([key]) => frame.policies[key].position === id) : [];
    const occupied = present.length > 0 || (frame && (frame.agentZone || frame.agent_zone || frame.position) === id);
    const colors = tileColors(zone);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tile " + (extraClass || "") + (zone.collapsed ? " collapsed" : "")
      + (occupied ? " occupied" : "") + (state.selectedZone === id ? " selected" : "");
    button.style.gridColumn = String(column);
    button.style.gridRow = rowSpan > 1 ? String(row) + " / span " + rowSpan : String(row);
    button.style.setProperty("--tile-bg", colors.bg);
    button.style.setProperty("--tile-border", colors.border);
    button.setAttribute("aria-label", zoneName(id) + t(", 불 ", ", fire ") + number(zone.fire)
      + t(", 연기 ", ", smoke ") + number(zone.smoke) + (zone.collapsed ? t(", 붕괴", ", collapsed") : "")
      + (occupied ? ", " + (present.length ? present.map(([, policy]) => policy.name).join(", ") : t("대피자 위치", "evacuee location")) : ""));
    const title = document.createElement("span");
    title.className = "tile-title";
    const shortName = id.endsWith("-ROOF") ? t("옥상", "Roof")
      : id.endsWith("-L") ? t("로비", "Lobby")
      : /-SA$/.test(id) ? t("계단 A", "Stairs A")
      : /-SB$/.test(id) ? t("계단 B", "Stairs B")
      : /-E$/.test(id) ? t("엘리베이터", "Elevator")
      : /-R(\d+)$/.test(id) ? t("방 ", "Room ") + /-R(\d+)$/.exec(id)[1]
      : t("복도 ", "Hall ") + /-C(\d+)$/.exec(id)[1];
    title.textContent = shortName;
    const values = document.createElement("span");
    values.className = "tile-values";
    const fire = document.createElement("span"); fire.textContent = t("불 ", "Fire ") + number(zone.fire);
    const smoke = document.createElement("span"); smoke.textContent = t("연기 ", "Smoke ") + number(zone.smoke);
    values.append(fire, smoke);
    button.append(title, values);
    if (present.length) {
      const markers = document.createElement("span");
      markers.className = "agent-markers";
      markers.setAttribute("aria-hidden", "true");
      for (const [key, policy] of present) {
        const marker = document.createElement("span");
        marker.className = "agent-marker " + key;
        marker.textContent = policy.marker;
        markers.append(marker);
      }
      button.append(markers);
    } else if (occupied) {
      const marker = document.createElement("span");
      marker.className = "agent-marker";
      marker.textContent = "人";
      marker.setAttribute("aria-hidden", "true");
      button.append(marker);
    }
    button.addEventListener("click", () => {
      state.selectedZone = id;
      renderPlan();
      renderDetails();
    });
    return button;
  }

  function renderFloorTabs() {
    const frame = currentFrame();
    const currentAgentFloor = agentFloor(frame);
    const fragment = document.createDocumentFragment();
    for (let floor = 1; floor <= 11; floor += 1) {
      const button = document.createElement("button");
      button.type = "button";
      const present = frame?.policies
        ? policyEntries.filter(([key]) => positionFloor(frame.policies[key].position) === floor) : [];
      button.textContent = (floor === 11 ? t("옥상", "Roof") : floor + "F")
        + (present.length ? " · " + present.map(([, policy]) => policy.marker).join(" ") : "");
      button.className = (state.floor === floor ? "active" : "")
        + ((present.length || currentAgentFloor === floor) ? " contains-agent" : "");
      button.setAttribute("aria-pressed", String(state.floor === floor));
      button.addEventListener("click", () => {
        state.floor = floor;
        el.follow.checked = false;
        renderFloorTabs();
        renderPlan();
        renderDetails();
      });
      fragment.append(button);
    }
    el.floorTabs.replaceChildren(fragment);
  }

  function renderPlan() {
    const floor = state.floor;
    el.floorTitle.textContent = floor === 11 ? zoneName("F11-ROOF") : t(`${floor}층 평면도`, `Floor ${floor} plan`);
    el.floorplan.replaceChildren();
    if (floor === 11) {
      const stage = document.createElement("div");
      stage.className = "roof-stage";
      stage.append(makeTile("F11-ROOF", 1, 1, 1, "roof-tile"));
      const label = document.createElement("span");
      label.className = "roof-label";
      label.textContent = t("10층 비상계단 A · B와 연결", "Connected to floor 10 by stairs A and B");
      stage.append(label);
      el.floorplan.append(stage);
      return;
    }
    const grid = document.createElement("div");
    grid.className = "building-grid";
    grid.append(makeTile("F" + floor + "-SA", 1, 1, 3, "tile-stair"));
    grid.append(makeTile("F" + floor + "-SB", 7, 1, 3, "tile-stair"));
    if (floor === 1) {
      grid.append(makeTile("F1-R1", 2, 1, 1), makeTile("F1-R2", 3, 1, 1));
      grid.append(makeTile("F1-E", 4, 1, 1), makeTile("F1-R3", 5, 1, 1));
      grid.append(makeTile("F1-R4", 6, 1, 1), makeTile("F1-L", "2 / 7", 2, 2, "lobby-tile"));
      const exits = document.createElement("div");
      exits.className = "exit-markers";
      const left = document.createElement("span"), right = document.createElement("span");
      left.textContent = t("↓ 출입구 1", "↓ Exit 1"); right.textContent = t("↓ 출입구 2", "↓ Exit 2");
      exits.append(left, right);
      grid.append(exits);
    } else {
      for (let room = 1; room <= 5; room += 1) grid.append(makeTile("F" + floor + "-R" + room, room + 1, 1, 1));
      for (let corridor = 1; corridor <= 5; corridor += 1) grid.append(makeTile("F" + floor + "-C" + corridor, corridor + 1, 2, 1));
      grid.append(makeTile("F" + floor + "-R6", 2, 3, 1), makeTile("F" + floor + "-R7", 3, 3, 1));
      grid.append(makeTile("F" + floor + "-E", 4, 3, 1), makeTile("F" + floor + "-R8", 5, 3, 1));
      grid.append(makeTile("F" + floor + "-R9", 6, 3, 1));
    }
    el.floorplan.append(grid);
  }

  function renderSummary() {
    const replay = state.replay, frame = currentFrame();
    if (!replay || !frame) {
      el.time.textContent = "--:--"; el.timeTotal.textContent = "/ --:--";
      el.agent.textContent = t("대기 중", "Waiting"); el.startValue.textContent = t("시작 방 선택 전", "Starting room pending");
      el.ignition.textContent = "—"; el.windValue.textContent = t("풍속 —", "Wind —");
      el.outcome.textContent = "—"; el.outcomeDetail.textContent = t("재생을 만들어 주세요", "Generate a replay");
      return;
    }
    const last = replay.frames[replay.frames.length - 1];
    el.time.textContent = clock(frame.second);
    el.timeTotal.textContent = "/ " + clock(last.second);
    el.ignition.textContent = zoneName(replay.ignitionId || replay.ignition_room);
    el.windValue.textContent = t("풍속 ", "Wind ") + (replay.wind ?? replay.wind_mps) + " m/s";
    if (replay.policies) {
      const rescued = Object.values(replay.policies).filter(track => ["exit", "roof", "room"].includes(track.outcome));
      el.agent.textContent = zoneName(replay.start_room);
      el.startValue.textContent = t("시드 ", "Seed ") + replay.seed;
      el.outcome.textContent = rescued.length + t(" / 2 구조", " / 2 rescued");
      el.outcomeDetail.textContent = t("이 시나리오의 최종 결과", "Final outcome for this scenario");
      return;
    }
    el.agent.textContent = zoneName(frame.agentZone || frame.agent_zone || frame.position);
    el.startValue.textContent = t("시작 ", "Start ") + zoneName(replay.startRoom || replay.start_room);
    el.outcome.textContent = outcomeName(replay.outcome);
    el.outcomeDetail.textContent = t("최종 시각 ", "End time ") + clock(last.second);
  }

  function renderComparison(frame) {
    const replay = state.replay;
    const rules = replay?.rules;
    el.rules.textContent = rules
      ? t(`공통 인지 지연 ${clock(rules.awareness_seconds)} · 이동 ${rules.action_seconds}/${rules.slow_move_seconds}초 · 사망 불 ≥${rules.fire_death_at}, 연기 ≥${rules.smoke_death_at} 또는 붕괴 · 옥상 구조 ${clock(rules.roof_rescue_at)} · 방 구조 ${clock(rules.room_rescue_at)}부터 (불 ≤${rules.room_rescue_fire_max})`,
        `Shared awareness delay ${clock(rules.awareness_seconds)} · travel ${rules.action_seconds}/${rules.slow_move_seconds} s · fatal fire ≥${rules.fire_death_at}, smoke ≥${rules.smoke_death_at}, or collapse · roof rescue from ${clock(rules.roof_rescue_at)} · room rescue from ${clock(rules.room_rescue_at)} (fire ≤${rules.room_rescue_fire_max})`)
      : t("두 정책에 같은 발화 방, 시작 방, 인지 지연, 이동 시간과 구조·사망 규칙을 적용합니다.", "Both policies share the ignition room, starting room, awareness delay, travel times and outcome rules.");
    byId("dijkstra-description").textContent = rules
      ? t(`출구를 탐색할 때 불 ≥${rules.dijkstra_fire_block}, 연기 ≥${rules.dijkstra_smoke_block} 또는 붕괴 구역을 제외합니다.`,
        `Exit routing excludes zones with fire ≥${rules.dijkstra_fire_block}, smoke ≥${rules.dijkstra_smoke_block}, or collapse.`)
      : t("위험도를 반영해 출구까지의 경로를 다시 계산합니다.", "Recalculates an exit route based on current hazards.");
    for (const [key] of policyEntries) {
      const current = frame?.policies?.[key];
      const result = replay?.policies?.[key];
      const decisions = result?.decisions || [];
      const waited = decisions.filter(decision => decision.action === "wait").length;
      byId(key + "-outcome").textContent = result ? t("최종 ", "Final · ") + trackOutcome(result) : "—";
      byId(key + "-actions").textContent = result ? t(`이동 ${decisions.length - waited}회 · 대기 ${waited}회`, `${decisions.length - waited} moves · ${waited} waits`) : "—";
      byId(key + "-position").textContent = current ? zoneName(current.position) : "—";
      byId(key + "-action").textContent = current ? (current.outcome ? trackOutcome(current) : decisionLabel(current.decision)) : "—";
      document.querySelector(`[data-jump-policy="${key}"]`).disabled = !current;
      const visited = decisions.filter(decision => decision.action === "move" && decision.second <= frame?.second)
        .map(decision => decision.target);
      if (current?.position === "EXIT") visited.push("EXIT");
      byId(key + "-path").textContent = current ? [replay.start_room, ...visited].map(zoneName).join(" → ") : "—";
    }
  }

  function nearestAction() {
    const replay = state.replay;
    if (!replay) return null;
    for (let i = state.frameIndex; i >= 0; i -= 1) {
      const frame = replay.frames[i];
      if (frame.action != null && frame.action !== "") return frame;
    }
    return null;
  }

  function renderDetails() {
    const frame = currentFrame();
    const selectZone = t("평면도의 구역을 선택하세요", "Select a zone on the floor plan");
    const inspectZone = t("불과 연기 수치를 자세히 볼 수 있습니다.", "Inspect its fire and smoke indices.");
    if (!frame) {
      el.action.textContent = "—"; el.risk.textContent = "—"; el.reward.textContent = "—";
      el.selected.textContent = selectZone;
      el.selectedDetail.textContent = inspectZone;
      return;
    }
    if (!frame.policies) {
      const actionFrame = nearestAction();
      el.action.textContent = actionFrame ? actionName(actionFrame.action) : t("화재 인지 전", "Awaiting fire awareness");
      const agentId = frame.agentZone || frame.agent_zone || frame.position;
      const agentZone = frame.zones && frame.zones[agentId];
      el.risk.textContent = agentZone
        ? t("불 ","Fire ") + number(agentZone.fire) + t(" · 연기 "," · Smoke ") + number(agentZone.smoke) + (agentZone.collapsed ? t(" · 붕괴"," · Collapsed") : "")
        : agentId === "EXIT" || agentId === "OUTSIDE" ? t("건물 밖","Outside") : "—";
      el.reward.textContent = actionFrame && actionFrame.reward != null ? number(actionFrame.reward) : "—";
    }
    const zone = state.selectedZone && frame.zones ? frame.zones[state.selectedZone] : null;
    el.selected.textContent = zone ? zoneName(state.selectedZone) : selectZone;
    el.selectedDetail.textContent = zone
      ? t("불 ","Fire ") + number(zone.fire) + t(" / 100 · 연기 "," / 100 · Smoke ") + number(zone.smoke) + " / 100"
        + (zone.collapsed ? t(" · 붕괴되어 이동 불가", " · Impassable due to collapse") : "")
      : inspectZone;
  }

  function renderEvents() {
    el.events.replaceChildren();
    const frame = currentFrame();
    if (!frame) {
      const empty = document.createElement("p"); empty.className = "empty";
      empty.textContent = t("재생을 만들면 기록이 표시됩니다.", "Generate a replay to see events.");
      el.events.append(empty);
      return;
    }
    const visible = state.events.filter((item) => Number(item.second) <= Number(frame.second)).slice(-15).reverse();
    if (!visible.length) {
      const empty = document.createElement("p"); empty.className = "empty";
      empty.textContent = t("이 시점까지 기록된 행동이 없습니다.", "No actions were recorded before this frame.");
      el.events.append(empty);
      return;
    }
    for (const item of visible) {
      const row = document.createElement("div"); row.className = "event-row";
      const time = document.createElement("time"); time.textContent = clock(item.second);
      const message = document.createElement("p"); message.textContent = item.text;
      row.append(time, message); el.events.append(row);
    }
  }

  function renderTimeline() {
    const replay = state.replay;
    const frames = replay && replay.frames;
    const hasFrames = !!(frames && frames.length);
    el.range.disabled = !hasFrames;
    el.play.disabled = !hasFrames || frames.length < 2;
    el.back.disabled = !hasFrames || state.frameIndex <= 0;
    el.next.disabled = !hasFrames || state.frameIndex >= frames.length - 1;
    el.jumpAgent.disabled = !hasFrames || agentFloor(currentFrame()) == null;
    el.range.max = hasFrames ? String(frames.length - 1) : "0";
    el.range.value = hasFrames ? String(state.frameIndex) : "0";
    el.timelineCurrent.textContent = hasFrames ? clock(frames[state.frameIndex].second) : "00:00";
    el.timelineEnd.textContent = hasFrames ? clock(frames[frames.length - 1].second) : "00:00";
  }

  function render() {
    const frame = currentFrame();
    const af = agentFloor(frame);
    if (el.follow.checked && af != null) state.floor = af;
    renderSummary();
    if (comparisonMode()) renderComparison(frame);
    renderFloorTabs();
    renderPlan();
    renderDetails();
    renderEvents();
    renderTimeline();
  }

  function metricSeries(metric) {
    const data = state.metrics;
    if (!data) return [];
    if (Array.isArray(data[metric])) return data[metric].map(Number);
    if (Array.isArray(data.history)) return data.history.map((item) => Number(item[metric]));
    return [];
  }

  function metricSteps(count) {
    const data = state.metrics || {};
    const source = Array.isArray(data.steps) ? data.steps
      : Array.isArray(data.timesteps) ? data.timesteps : [];
    return Array.from({length: count}, (_, i) => Number(source[i]) || i);
  }

  function drawChart() {
    const canvas = el.lossChart;
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(300, Math.round(rect.width || 640));
    const height = Math.max(160, Math.round(rect.height || 225));
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.fillStyle = "#0d1b2a"; ctx.fillRect(0, 0, width, height);
    const metric = el.lossSelect.value;
    const label = el.lossSelect.selectedOptions[0].textContent;
    const series = metricSeries(metric);
    const steps = metricSteps(series.length);
    const points = series.map((value, index) => ({x: steps[index], y: value}))
      .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
    const success = metricSeries("eval_success").filter(Number.isFinite).at(-1);
    el.evalReadout.textContent = success == null ? ""
      : t("평가 성공률 ", "Evaluation success rate ") + (success <= 1 ? (success * 100).toFixed(1) : success.toFixed(1)) + "%";
    if (!points.length) {
      ctx.fillStyle = "#8ca7bc"; ctx.font = "12px Segoe UI, Malgun Gothic, sans-serif";
      ctx.textAlign = "center"; ctx.fillText(t("표시할 학습 기록이 없습니다.", "No training data to display."), width / 2, height / 2);
      el.lossReadout.textContent = state.metricsFailed ? t("학습 기록을 읽지 못했습니다.", "Cannot read the training logs.")
        : t("학습이 끝나면 손실 변화를 볼 수 있습니다.", "Training loss will appear when logs are available.");
      return;
    }
    const left = 56, right = width - 15, top = 18, bottom = height - 29;
    const minX = Math.min(...points.map((p) => p.x)), maxX = Math.max(...points.map((p) => p.x));
    let minY = Math.min(...points.map((p) => p.y)), maxY = Math.max(...points.map((p) => p.y));
    const padding = Math.max((maxY - minY) * .12, Math.abs(maxY) * .015, .0001);
    minY -= padding; maxY += padding;
    ctx.font = "10px Segoe UI, Malgun Gothic, sans-serif";
    ctx.textAlign = "right"; ctx.strokeStyle = "#284055"; ctx.fillStyle = "#8ba6b8";
    for (let i = 0; i <= 4; i += 1) {
      const y = top + i * (bottom - top) / 4;
      ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
      ctx.fillText((maxY - i * (maxY - minY) / 4).toFixed(2), left - 8, y + 3);
    }
    const xScale = (x) => left + (maxX === minX ? 0 : (x - minX) / (maxX - minX) * (right - left));
    const yScale = (y) => bottom - (y - minY) / (maxY - minY) * (bottom - top);
    ctx.textAlign = "center";
    ctx.fillText(String(Math.round(minX)), left, height - 8);
    ctx.fillText(String(Math.round(maxX)), right, height - 8);
    ctx.beginPath();
    points.forEach((p, i) => i === 0 ? ctx.moveTo(xScale(p.x), yScale(p.y)) : ctx.lineTo(xScale(p.x), yScale(p.y)));
    ctx.strokeStyle = "#f5a179"; ctx.lineWidth = 2; ctx.stroke();
    const last = points[points.length - 1];
    ctx.beginPath(); ctx.arc(xScale(last.x), yScale(last.y), 3.5, 0, Math.PI * 2);
    ctx.fillStyle = "#ffd0aa"; ctx.fill();
    const stepsLabel = Math.round(last.x).toLocaleString(getLanguage());
    el.lossReadout.textContent = label + t(` · 마지막 ${last.y.toFixed(4)} · 학습 행동 ${stepsLabel}회`, ` · Latest ${last.y.toFixed(4)} · ${stepsLabel} training actions`);
  }

  function renderModeLabels() {
    const compare = comparisonMode();
    const comparisonOnly = ["comparison-settings", "comparison-results", "follow-policy-field", "dijkstra-legend", "ppo-legend"];
    const reviewOnly = ["ppo-run-options", "charts-panel", "single-details", "single-legend", "jump-agent"];
    for (const id of comparisonOnly) byId(id).hidden = !compare;
    for (const id of reviewOnly) byId(id).hidden = compare;
    byId("agent-label").textContent = compare ? t("공통 시작 방", "Shared starting room") : t("대피자 위치", "Evacuee location");
    byId("detail-heading").textContent = compare ? t("구역 위험도", "Zone Hazards") : t("대피 판단", "Evacuation Decisions");
    byId("page-description").textContent = compare ? t("같은 화재와 대피 규칙에서 다익스트라와 PPO를 재생합니다.", "Replay Dijkstra and PPO against the same fire and evacuation rules.")
      : t("저장된 PPO 모델의 이동과 학습 기록을 확인합니다.", "Review a saved PPO model's movement and training history.");
    el.generate.textContent = compare ? t("비교 재생 만들기", "Generate comparison") : t("선택한 모델로 재생 만들기", "Generate model replay");
  }

  function updateMode() {
    renderModeLabels();
    state.requestId += 1;
    clearReplay();
    showSelection();
    if (!comparisonMode()) loadRuns();
  }

  el.mode.addEventListener("change", updateMode);
  el.run.addEventListener("change", () => {
    clearReplay();
    showSelection();
    loadMetrics();
  });
  el.refresh.addEventListener("click", () => offlineMode ? el.folderInput.click() : loadRuns());
  el.folderInput.addEventListener("change", async () => {
    try { await importOfflineFiles(el.folderInput.files, true); }
    catch (error) { setNotice(t("모델을 불러오지 못했습니다: ", "Cannot load the model. ") + sourceText(error.message), "error"); }
    finally { el.folderInput.value = ""; }
  });
  el.policyInput.addEventListener("change", async () => {
    try { await importOfflineFiles(el.policyInput.files, false); }
    catch (error) { setNotice(t("모델을 불러오지 못했습니다: ", "Cannot load the model. ") + sourceText(error.message), "error"); }
    finally { el.policyInput.value = ""; }
  });
  el.generate.addEventListener("click", generate);
  el.play.addEventListener("click", () => state.timer === null ? play() : pause());
  el.back.addEventListener("click", () => moveFrame(state.frameIndex - 1));
  el.next.addEventListener("click", () => moveFrame(state.frameIndex + 1));
  el.range.addEventListener("input", () => moveFrame(Number(el.range.value)));
  el.speed.addEventListener("change", () => { if (state.timer !== null) { pause(); play(); } });
  el.jumpAgent.addEventListener("click", () => {
    const floor = agentFloor(currentFrame());
    if (floor != null) { state.floor = floor; renderFloorTabs(); renderPlan(); renderDetails(); }
  });
  el.follow.addEventListener("change", render);
  el.followPolicy.addEventListener("change", () => { el.follow.checked = true; render(); });
  for (const button of document.querySelectorAll("[data-jump-policy]")) {
    button.addEventListener("click", () => {
      el.followPolicy.value = button.dataset.jumpPolicy;
      el.follow.checked = true;
      render();
      el.floorTitle.scrollIntoView({block: "nearest"});
    });
  }
  el.lossSelect.addEventListener("change", drawChart);
  window.addEventListener("resize", () => { if (!comparisonMode()) drawChart(); });
  window.addEventListener("message", (event) => {
    if (event.origin !== location.origin || event.source !== window.parent) return;
    if (event.data === "pause-model-replay") pause();
    if (event.data?.type === "fireroute-language") locale.setLanguage(event.data.language);
  });

  locale.onChange(() => {
    locale.localize(document);
    renderModeLabels();
    for (const select of [el.ignitionSelect, el.start]) {
      for (const option of select.options) if (option.value) option.textContent = zoneName(option.value);
    }
    if (!comparisonMode()) {
      showRuns(el.run.value, {refreshMetrics: false});
      drawChart();
    }
    const replay = state.replay;
    if (replay) state.events = replay.policies ? comparisonEvents(replay) : extractEvents(replay.frames);
    if (state.generating) showGenerating();
    else if (replay) showReady(replay);
    else showSelection();
    renderPlayLabel();
    render();
  });
  el.offlineImport.hidden = false;
  if (offlineMode) {
    el.refresh.textContent = t("다른 runs 폴더 선택", "Select another runs folder");
    el.mode.value = "ppo";
    byId("mode-field").hidden = true;
  }
  fillRoomSelect(el.ignitionSelect);
  fillRoomSelect(el.start);
  updateMode();
  if (!offlineMode) setInterval(() => { if (!comparisonMode() && isTraining(selectedRun())) loadRuns(); }, 5000);
})();
