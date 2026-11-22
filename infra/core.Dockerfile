ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
ARG WITH_POLICY_COMPARISON=0
RUN if [ "$WITH_POLICY_COMPARISON" = "1" ]; then python -m pip install --no-cache-dir numpy==2.1.3; fi
COPY backend/ backend/
COPY onem2m/ onem2m/
COPY simulator/ simulator/
COPY mec/ mec/
COPY fixtures/ fixtures/
COPY frontend/ frontend/
COPY tests/ tests/
COPY infra/ infra/
COPY compose.yaml compose.standards.yaml compose.https.yaml compose.cse-security.yaml compose.mec-local.yaml compose.mec-runtime.yaml compose.mec-services.yaml pyproject.toml Makefile .python-version .node-version LICENSE README.md ./
ENTRYPOINT ["python", "-m", "backend.p0"]
