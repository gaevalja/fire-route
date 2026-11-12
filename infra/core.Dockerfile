ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/ backend/
COPY onem2m/ onem2m/
COPY simulator/ simulator/
COPY mec/ mec/
COPY fixtures/ fixtures/
COPY frontend/ frontend/
COPY tests/ tests/
COPY infra/ infra/
COPY compose.yaml pyproject.toml Makefile .python-version LICENSE README.md ./
ENTRYPOINT ["python", "-m", "backend.p0"]
