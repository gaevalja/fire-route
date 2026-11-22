# Local official MEC011 runtime and FireRoute integration

The subsequent [FireRoute service/IPE/dashboard increment](MEC_SERVICES.md) is implemented for separate actual validation with make p1-mec-services; its interactive command is make demo-mec-up on port 3002. The earlier seven-check profile below stays the verified component baseline. New runtime success has not yet been claimed.

The user explicitly requests local MEC integration and excludes video work. Both official STF_685 repositories are now acquired and reviewed. The runtime below builds the official App Enablement component directly, alongside Redis and a separate actual ACME CSE. This is an actual upstream service process, not a FireRoute replacement MEC server. It is a bounded local component deployment, not the complete Kubernetes Sandbox/UI, an orchestrator, VM placement or TR-0086 Option C.

Actual result: user make p1-mec-local at evidence/20261116-114543Z-372e392f passes all seven native checks, with actual component/CSE/Redis startup and healthy services. Catalog service_count=0 is expected for this fresh unseeded profile. The application-AE bridge is verified for discovery metadata; FireRoute risk-app registration, consumption, manager-controlled placement and official IPE remain open. The test client exits after the gate, while the three services remain running; this is not yet a continuous dashboard/MEC risk pipeline.

## Start and test

~~~bash
# Build/start the official MEC service, Redis and dedicated real CSE;
# wait for their actual healthchecks, then run the catalog/CSE/SUB/ACP gate.
make p1-mec-local

# Start or retain the three services for normal API inspection.
make mec-local-up

# Logs / stop only this separate project; named volumes remain.
make mec-local-logs
make mec-local-down
~~~

The first command leaves the three services running after the test client exits. Use one integration run at a time: the private callback uses the mec-check network alias. It is explicitly enabled with compose run --use-aliases. The existing dashboard/CSE on 3001/8080 is separate. The MEC component publishes only 127.0.0.1:8090; set MEC_LOCAL_PORT in ignored .env if that port is occupied. Redis and the dedicated CSE have no host ports. No system installer, Kubernetes setup, Docker daemon restart, host trust-store update, OAuth credential or Hosted access is involved.

Actual Service Management URL after successful startup: http://127.0.0.1:8090/mec_service_mgmt/v1/services. A fresh real catalog may correctly return []; the runtime does not seed service records, app IDs or scenario state. Empty discovery is not useful MEC service consumption, application lifecycle placement or IPE evidence. The worker/dashboard is not silently labeled MEC-connected by starting this separate profile.

## Exact source and build inputs

- Backend: 8c66f08e443be174f109fe2ac645247c9afcd449, tree aded204ff049309bd0c0bfea711c5bd290dc2615.
- Frontend: df11a72bd1d1520028a6d40cee1aed093cc1efad, retained/reviewed but not needed by this component runtime.
- Inspected source: go-apps/meep-app-enablement/main.go, server/app-enablement.go, server/routers.go, server/service-mgmt/service-mgmt.go, server/app-support/app-support.go, go-packages/meep-redis/db.go and module files. The included OpenAPI reports 3.1.1; actual route roots are mec_service_mgmt/v1 and mec_app_support/v2.
- The upstream Go service uses a fixed Redis FQDN. Compose provides that exact private network alias. Its JSON helpers use plain Redis GET/SET; no RedisJSON module is needed. No active scenario/InfluxDB logger is installed in this bounded profile. Upstream metric-store-not-initialised log messages are retained, not suppressed.

make mec-runtime-stage verifies the source locks, requires the reviewed backend commit/tree, and extracts 2,199 files from committed Git objects into ignored .runtime/mec-sandbox/runtime-build/source/. Untracked/ignored local settings never enter the image context. Existing staged edits are rejected rather than overwritten. The original official checkout remains unchanged. infra/mec/upstream.json records the reviewed identity and image choices.

The separate Dockerfile compiles the upstream Go program without source patches. Go 1.25.0 follows the acquired deployment configuration; Redis 6.2.24-bookworm is pinned from the [Docker Official Images listing](https://github.com/docker-library/official-images/blob/master/library/redis), using a legacy-compatible server series for the upstream go-redis v6 client. The user's actual build now completes Go compilation/module-report generation and image startup. Its terminal provides image tags/digests; the image's binary/module metadata has not been independently read. Go may update its module graph only in the disposable image build copy; the resulting go.mod/go.sum, resolved-go-modules.json, go-build-info.txt and upstream license remain under /opt/etsi-mec/. Original upstream dependency files are untouched. Direct component API paths are used; this does not install the Sandbox ingress/UI or promise a working Swagger Try-it-out host mapping.

## Actual CSE integration gate

mec.local_integration reads the real MEC011 response using the existing bounded/redacted catalog client. It then checks an actual CSEBase, registers distinct bridge/reader AEs, creates a dedicated expiring ACP/CNT/SUB, verifies the real subscription handshake, creates one catalog CIN, matches writer/reader read-back and durable notification, and requires reader CREATE denial HTTP 403/RSC 4103. No uncertain CREATE is replayed. The seven checks must actually execute before PASS is recorded.

Writer and reader are separate actual AE identities/clients within the same test process. The existing three independent display processes remain a different gate. Callback and CSE links remain private HTTP with development header identities; Redis is unauthenticated on its private network only. No full transport/authentication upgrade is claimed. Catalog snapshots preserve APPLICATION_AE_BRIDGE_NOT_MEC_IPE, approved metadata, response hash and observation time. No official IPE or deployment result is fabricated.

For an independently installed private local endpoint, retain the earlier external mode:

~~~bash
# Set actual MEC_LOCAL_SERVICE_MGMT_URL in ignored .env first.
make p1-mec-external
~~~

That mode has no built-in platform and rejects public/Hosted URLs, container loopback and unsupported authentication settings before contact. The original mec-discover / mec-catalog-to-cse commands retain their explicit CA/token configuration for configured authenticated endpoints.

## Verified and pending results

| Gate | Actual result |
|---|---|
| Official source acquisition | User run 20261116-062033Z-fbbbbe96 obtains both repositories; agent 20261116-064534Z-9a6586f6 rechecks exact locks/pristine trees |
| Runtime source preparation | 20261116-064118Z-1b2ee3ed stages 2,199 exact committed files; earlier parent-directory rejection 064010Z-fb0fee40 is fixed and retained |
| Compose/implementation | Merged topology parses and new source/health fixtures pass; final unit/static report is indexed in STATUS |
| Actual Go image build / service startup | User terminal completes Go/image builds; current MEC/Redis/CSE containers are healthy. Earlier agent-only Docker denial stays historical; image binary metadata is not independently read |
| Actual MEC → CSE integration | 20261116-114543Z-372e392f PASS 7; 16 native CSE exchanges, two callbacks, matching CIN and reader 403/4103; source/input reviews are indexed in STATUS |
| Whole Sandbox / app lifecycle / official IPE | Not completed by this component profile |

Run make mec-local-prepare only if the source is absent; make mec-local-inspect checks it without downloading/updating it. Original source-lock, runtime manifests and private evidence remain outside Git. Python application dependencies, the fire engine, movement assumptions, original proof and default-demo configuration are preserved.

Next service integration must use a real platform-assigned app instance and actual registration/discovery. In the acquired revision, official IPE initialization relies on app/service management beyond this component profile. The Sandbox controller's native allocation API also brings additional CouchDB/InfluxDB dependencies; inspect its configuration/security before deployment. A made-up UUID or manual Redis record is not a deployment result. Keep this passing component profile as the baseline while adding that supported path. Summary platform_deployment=NOT_VERIFIED refers to manager-controlled application placement, not a failure of the observed component-container startup.
