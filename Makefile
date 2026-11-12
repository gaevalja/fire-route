PYTHON ?= python3
SCENARIO_SEED ?= 2026
SCENARIO_WIND ?= 5
SCENARIO_SECONDS ?= 180

.PHONY: test test-unit test-frontend test-scenario scenario-trace scenario-preview p1-scenario p1-scenario-dashboard demo-scenario-up demo-scenario-logs test-cse test-routes test-group up-core down p0-smoke p1-routes p1-group compose-check access-codes demo-up demo-logs p1-dashboard

test: test-unit

test-unit:
	$(PYTHON) -m unittest discover -s tests/unit -v

test-frontend:
	node tests/frontend/model.test.mjs
	node tests/frontend/scenario-model.test.mjs

test-scenario:
	node simulator/scenarios/fire_evac/test_engine.js

scenario-trace:
	node simulator/export_scenario.cjs --seed $(SCENARIO_SEED) --wind $(SCENARIO_WIND) --seconds $(SCENARIO_SECONDS)

scenario-preview: scenario-trace
	$(PYTHON) -m simulator.replay

p1-scenario: scenario-trace
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile scenario up --build --abort-on-container-exit --exit-code-from scenario-core

p1-scenario-dashboard: scenario-trace access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile scenario-demo --profile scenario-check up --build --force-recreate --abort-on-container-exit --exit-code-from scenario-check

demo-scenario-up: SCENARIO_SECONDS=1800
demo-scenario-up: scenario-trace access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile scenario-demo up -d --build --force-recreate cse scenario-app

demo-scenario-logs:
	docker compose --profile scenario-demo logs --tail=100 scenario-app

test-cse:
	$(PYTHON) -m backend.p0

test-routes:
	$(PYTHON) -m backend.p1_routes

test-group:
	$(PYTHON) -m backend.p1_group

compose-check:
	docker compose --profile smoke --profile routes --profile group --profile dashboard --profile dashboard-check --profile scenario --profile scenario-demo --profile scenario-check config --quiet

up-core:
	docker compose up -d --build cse

down:
	docker compose --profile smoke --profile routes --profile group --profile dashboard --profile dashboard-check --profile scenario --profile scenario-demo --profile scenario-check down

p0-smoke:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile smoke up --build --abort-on-container-exit --exit-code-from p0

p1-routes:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile routes up --build --abort-on-container-exit --exit-code-from p1-routes

p1-group:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile group up --build --abort-on-container-exit --exit-code-from p1-group

access-codes:
	$(PYTHON) -m backend.auth

demo-up: access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile dashboard up -d --build cse app

demo-logs:
	docker compose --profile dashboard logs --tail=100 app

p1-dashboard: access-codes
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile dashboard --profile dashboard-check up --build --abort-on-container-exit --exit-code-from dashboard-check
