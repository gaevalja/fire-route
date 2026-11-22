FROM golang:1.25.0-bookworm AS build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
WORKDIR /src
COPY --from=etsi_source /go-packages/ ./go-packages/
COPY --from=etsi_source /go-apps/meep-sandbox-ctrl/ ./go-apps/meep-sandbox-ctrl/
COPY --from=etsi_source /LICENSE /out/UPSTREAM-LICENSE
COPY infra/mec/patch_couch_auth.py /tmp/patch_couch_auth.py
# The Python helper is interpreted in the final build-preparation stage below.
FROM python:3.12-slim-bookworm AS patched
COPY --from=build /src/ /src/
COPY infra/mec/patch_couch_auth.py /tmp/patch_couch_auth.py
RUN python /tmp/patch_couch_auth.py

FROM build AS compile
COPY --from=patched /src/go-packages/meep-couch/db.go /src/go-packages/meep-couch/db.go
WORKDIR /src/go-apps/meep-sandbox-ctrl
RUN go build -mod=mod -buildvcs=false -trimpath -o /out/meep-sandbox-ctrl . && \
    go list -mod=readonly -m -json all > /out/resolved-go-modules.json && \
    cp go.mod go.sum /out/ && go version -m /out/meep-sandbox-ctrl > /out/go-build-info.txt && \
    mkdir -p /out/api && cp api/swagger.yaml /out/api/sandbox-ctrl.yaml

FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.source="https://labs.etsi.org/rep/mec/etsi-mec-sandbox.git" \
      org.opencontainers.image.revision="8c66f08e443be174f109fe2ac645247c9afcd449" \
      fire-route.patch="Couch auth environment configuration only"
COPY --from=compile /out/ /opt/etsi-mec/
COPY --from=compile /out/api/ /api/
ENTRYPOINT ["/opt/etsi-mec/meep-sandbox-ctrl"]
