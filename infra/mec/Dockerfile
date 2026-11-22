ARG GO_IMAGE=golang:1.25.0-bookworm
FROM ${GO_IMAGE} AS build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
WORKDIR /src
COPY --from=etsi_source /go-packages/ ./go-packages/
COPY --from=etsi_source /go-apps/meep-app-enablement/ ./go-apps/meep-app-enablement/
COPY --from=etsi_source /LICENSE /out/UPSTREAM-LICENSE
WORKDIR /src/go-apps/meep-app-enablement
# Upstream local module replacements stay intact. Any Go graph updates occur
# only in this disposable build copy and are retained in the runtime image.
RUN go build -mod=mod -buildvcs=false -trimpath -o /out/meep-app-enablement .
RUN go list -mod=readonly -m -json all > /out/resolved-go-modules.json
RUN cp go.mod go.sum /out/ && go version -m /out/meep-app-enablement > /out/go-build-info.txt
RUN mkdir -p /out/api /out/user-api && \
    cp api/service-mgmt/swagger.yaml /out/api/service-mgmt.yaml && \
    cp api/app-support/swagger.yaml /out/api/app-support.yaml && \
    cp api/capif-mgmt/swagger.yaml /out/api/capif-mgmt.yaml

FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.source="https://labs.etsi.org/rep/mec/etsi-mec-sandbox.git" \
      org.opencontainers.image.revision="8c66f08e443be174f109fe2ac645247c9afcd449"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /out/ /opt/etsi-mec/
COPY --from=build /out/api/ /api/
COPY --from=build /out/user-api/ /user-api/
COPY infra/mec/healthcheck.py /opt/fire-route/mec-healthcheck.py
COPY infra/mec/upstream.json /opt/etsi-mec/upstream.json
WORKDIR /
# Run the unmodified upstream program. No application IDs, service records,
# scenario models or API responses are preloaded into Redis.
ENTRYPOINT ["/opt/etsi-mec/meep-app-enablement"]
