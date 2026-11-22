FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Optional binding test dependency, not a dependency of the main application.
COPY infra/mqtt-requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ backend/
COPY onem2m/ onem2m/
COPY simulator/ simulator/
COPY mec/ mec/
COPY fixtures/ fixtures/
COPY tests/ tests/
COPY infra/ infra/
COPY frontend/ frontend/
COPY compose.yaml compose.standards.yaml compose.https.yaml pyproject.toml Makefile .python-version .node-version ./
ENTRYPOINT ["python", "-m", "tests.integration.standards_check"]
