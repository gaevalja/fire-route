PYTHON ?= python3

.PHONY: test test-unit test-cse test-routes test-group up-core down p0-smoke p1-routes p1-group compose-check

test: test-unit

test-unit:
	$(PYTHON) -m unittest discover -s tests/unit -v

test-cse:
	$(PYTHON) -m backend.p0

test-routes:
	$(PYTHON) -m backend.p1_routes

test-group:
	$(PYTHON) -m backend.p1_group

compose-check:
	docker compose --profile smoke --profile routes --profile group config --quiet

up-core:
	docker compose up -d --build cse

down:
	docker compose --profile smoke --profile routes --profile group down

p0-smoke:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile smoke up --build --abort-on-container-exit --exit-code-from p0

p1-routes:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile routes up --build --abort-on-container-exit --exit-code-from p1-routes

p1-group:
	LOCAL_UID=$$(id -u) LOCAL_GID=$$(id -g) docker compose --profile group up --build --abort-on-container-exit --exit-code-from p1-group
