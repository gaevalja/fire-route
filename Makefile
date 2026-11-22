PYTHON ?= python3
SCENARIO_SEED ?= 2026
SCENARIO_WIND ?= 5
SCENARIO_SECONDS ?= 180
HAZARD_SEED ?= 59
HAZARD_WIND ?= 5
HAZARD_SECONDS ?= 1800

.PHONY: test test-unit test-frontend test-scenario scenario-trace scenario-preview hazard-trace hazard-preview diagnose-cse local-stability p1-hazards p1-scenario p1-scenario-dashboard demo-scenario-up demo-scenario-logs test-cse test-routes test-group up-core down p0-smoke p1-routes p1-group compose-check access-codes demo-up demo-logs p1-dashboard

test: test-unit

test-unit:
	$(PYTHON) -m unittest discover -s tests/unit -v

test-frontend:
	node tests/frontend/model.test.mjs
	node tests/frontend/scenario-model.test.mjs
	node tests/frontend/building-view.test.mjs
	node tests/frontend/timeline.test.mjs
	node tests/frontend/locale.test.mjs

test-scenario:
	node simulator/scenarios/fire_evac/test_engine.js

scenario-trace:
	node simulator/export_scenario.cjs --seed $(SCENARIO_SEED) --wind $(SCENARIO_WIND) --seconds $(SCENARIO_SECONDS)

scenario-preview: scenario-trace
	$(PYTHON) -m simulator.replay

hazard-trace:
	node simulator/export_scenario.cjs --seed $(HAZARD_SEED) --wind $(HAZARD_WIND) --seconds $(HAZARD_SECONDS) --output .runtime/fire-evac-hazards.jsonl

hazard-preview: hazard-trace
	$(PYTHON) -m simulator.hazard_preview

p1-hazards: hazard-trace
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile hazards up --build --force-recreate --abort-on-container-exit --exit-code-from scenario-hazards

.PHONY: fault-trace p1-faults recovery-trace p1-recovery latency-trace p1-latency
fault-trace:
	node simulator/export_scenario.cjs --seed 59 --wind 5 --seconds 470 --output .runtime/fire-evac-faults.jsonl

p1-faults: fault-trace
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile faults up --build --force-recreate --abort-on-container-exit --exit-code-from scenario-faults

recovery-trace:
	node simulator/export_scenario.cjs --seed 59 --wind 5 --seconds 470 --output .runtime/fire-evac-recovery.jsonl

p1-recovery: recovery-trace
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) $(PYTHON) -m infra.cse_recovery

latency-trace:
	node simulator/export_scenario.cjs --seed 2026 --wind 5 --seconds 34 --output .runtime/fire-evac-latency.jsonl

p1-latency: latency-trace
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile latency up --build --force-recreate --abort-on-container-exit --exit-code-from scenario-latency

diagnose-cse:
	$(PYTHON) -m infra.cse.diagnostics

.PHONY: inspect-cse-runtime
inspect-cse-runtime:
	$(PYTHON) -m infra.cse.runtime_audit

local-stability:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) $(PYTHON) -m infra.local_stability

p1-scenario: scenario-trace
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile scenario up --build --abort-on-container-exit --exit-code-from scenario-core

p1-scenario-dashboard: scenario-trace access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile scenario-demo --profile scenario-check up --build --force-recreate --abort-on-container-exit --exit-code-from scenario-check

demo-scenario-up: SCENARIO_SECONDS=1800
demo-scenario-up: scenario-trace access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile scenario-demo up -d --build --force-recreate --wait --wait-timeout 120 cse scenario-app

demo-scenario-logs:
	docker compose --profile scenario-demo logs --tail=100 scenario-app

test-cse:
	$(PYTHON) -m backend.p0

test-routes:
	$(PYTHON) -m backend.p1_routes

test-group:
	$(PYTHON) -m backend.p1_group

compose-check:
	docker compose --profile smoke --profile routes --profile group --profile dashboard --profile dashboard-check --profile scenario --profile scenario-demo --profile scenario-check --profile hazards --profile stability --profile analysis --profile faults --profile recovery --profile latency config --quiet

up-core:
	docker compose up -d --build cse

down:
	docker compose --profile smoke --profile routes --profile group --profile dashboard --profile dashboard-check --profile scenario --profile scenario-demo --profile scenario-check --profile hazards --profile stability --profile analysis --profile faults --profile recovery --profile latency down

p0-smoke:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile smoke up --build --abort-on-container-exit --exit-code-from p0

p1-routes:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile routes up --build --abort-on-container-exit --exit-code-from p1-routes

p1-group:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile group up --build --abort-on-container-exit --exit-code-from p1-group

access-codes:
	$(PYTHON) -m backend.auth

.PHONY: test-browser-driver test-browser p1-browser p1-standards tls-files demo-secure-up test-https verify-local verify-clean
test-browser-driver:
	node tests/browser/cdp.test.mjs
	node tests/browser/controls.test.mjs
	node tests/browser/fonts.test.mjs

test-browser:
	node tests/browser/dashboard.mjs

p1-browser: demo-scenario-up
	node tests/browser/dashboard.mjs

.PHONY: record-demo standards-down
record-demo: demo-scenario-up
	node tests/browser/dashboard.mjs --record

standards-down:
	docker compose -p $${COMPOSE_PROJECT_NAME:-fire-route}-standards -f compose.standards.yaml down

p1-standards:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose -p $${COMPOSE_PROJECT_NAME:-fire-route}-standards -f compose.standards.yaml up --build --abort-on-container-exit --exit-code-from standards

tls-files:
	$(PYTHON) -m infra.dev_tls

demo-secure-up: SCENARIO_SECONDS=1800
demo-secure-up: scenario-trace access-codes tls-files
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose -f compose.yaml -f compose.https.yaml --profile scenario-demo up -d --build --force-recreate --wait --wait-timeout 120 cse scenario-app

test-https:
	$(PYTHON) -m tests.integration.tls_check

verify-local:
	$(PYTHON) -m infra.local_release

verify-clean:
	$(PYTHON) -m infra.local_release --clean-checkout

.PHONY: cse-mtls-files p1-cse-security cse-security-down
cse-mtls-files:
	$(PYTHON) -m infra.cse.pki

p1-cse-security: cse-mtls-files
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose -p fire-route-security -f compose.cse-security.yaml up --build --abort-on-container-exit --exit-code-from secure-check

cse-security-down:
	docker compose -p fire-route-security -f compose.cse-security.yaml down

.PHONY: mec-discover mec-catalog-to-cse
mec-discover:
	$(PYTHON) -m mec.probe

mec-catalog-to-cse:
	$(PYTHON) -m mec.probe --persist-onem2m

.PHONY: mec-local-prepare mec-local-inspect mec-runtime-stage mec-local-up p1-mec-local p1-mec-external mec-local-down mec-local-logs
mec-local-prepare:
	$(PYTHON) -m infra.mec_local

mec-local-inspect:
	$(PYTHON) -m infra.mec_local --inspect

mec-runtime-stage:
	$(PYTHON) -m infra.mec_runtime

mec-local-up: mec-runtime-stage
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose -p fire-route-mec-local -f compose.mec-local.yaml -f compose.mec-runtime.yaml up -d --build --wait --wait-timeout 180 mec-redis mec-platform mec-cse

p1-mec-local: mec-local-up
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose -p fire-route-mec-local -f compose.mec-local.yaml -f compose.mec-runtime.yaml run --build --rm --no-deps --use-aliases mec-check

p1-mec-external:
	$(PYTHON) -m mec.local_integration --preflight
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose -p fire-route-mec-local -f compose.mec-local.yaml up --build --abort-on-container-exit --exit-code-from mec-check

mec-local-down:
	docker compose -p fire-route-mec-local -f compose.mec-local.yaml -f compose.mec-runtime.yaml down

mec-local-logs:
	docker compose -p fire-route-mec-local -f compose.mec-local.yaml -f compose.mec-runtime.yaml logs --tail=50 mec-platform mec-redis mec-cse

.PHONY: mec-services-prepare mec-services-up p1-mec-services mec-services-down mec-services-logs
mec-services-prepare:
	$(PYTHON) -m infra.mec_services

mec-services-up: mec-services-prepare
	docker compose -p fire-route-mec-services -f compose.mec-services.yaml up -d --build --wait --wait-timeout 240 mec-ipe

p1-mec-services:
	node simulator/export_scenario.cjs --seed $(HAZARD_SEED) --wind $(HAZARD_WIND) --seconds $(HAZARD_SECONDS) --output .runtime/fire-evac-mec.jsonl
	$(MAKE) mec-services-up
	docker compose -p fire-route-mec-services -f compose.mec-services.yaml run --build --rm --no-deps --use-aliases mec-services-check
	$(MAKE) p1-mec-dashboard

mec-services-down:
	docker compose -p fire-route-mec-services -f compose.mec-services.yaml down

mec-services-logs:
	docker compose -p fire-route-mec-services -f compose.mec-services.yaml logs --tail=50 mec-controller mec-platform mec-risk mec-occupancy mec-ipe mec-cse

.PHONY: demo-mec-up p1-mec-dashboard
demo-mec-up: access-codes mec-services-prepare
	node simulator/export_scenario.cjs --seed 59 --wind 5 --seconds 1800 --output .runtime/fire-evac-mec-demo.jsonl
	docker compose -p fire-route-mec-services -f compose.mec-services.yaml --profile mec-dashboard up -d --build --wait --wait-timeout 240 mec-dashboard

p1-mec-dashboard: demo-mec-up
	docker compose -p fire-route-mec-services -f compose.mec-services.yaml --profile mec-dashboard --profile mec-dashboard-check run --build --rm --no-deps mec-dashboard-check

demo-up: access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile dashboard up -d --build cse app

demo-logs:
	docker compose --profile dashboard logs --tail=100 app

p1-dashboard: access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile dashboard --profile dashboard-check up --build --abort-on-container-exit --exit-code-from dashboard-check
