ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY infra/cse/requirements.txt /opt/cse-requirements.txt
RUN python -m pip install --no-cache-dir -r /opt/cse-requirements.txt
COPY infra/cse/acme.ini /etc/fire-route/acme.ini
COPY infra/cse/entrypoint.py infra/cse/healthcheck.py /opt/fire-route/
WORKDIR /data
ENTRYPOINT ["python", "/opt/fire-route/entrypoint.py"]
