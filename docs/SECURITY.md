# Certificate-bound CSE security profile

This opt-in profile places an NGINX mTLS gateway in front of the actual ACME CSE. It is not a replacement CSE. The existing demo and its volumes remain separate. Actual T36 evidence/20261116-040708Z-ba53f73b/ now passes all 11 checks on source manifest f8aac0f7fc95f404a809cc529f6858c7e1ae709c081db1d26532bd830b095492, matching published aa79ace. Separate read-only review evidence/20261116-042739Z-0906daca/ passes 18 checks over 48 native CSE exchanges, two callbacks and eight public certificates. The boundaries below still apply; this is not a secure full-scenario or MEC result.

## Trust and request flow

Client AE → TLS 1.2+ with client certificate → NGINX → private ACME HTTP binding.

The local CA signs a separate certificate whose CN is the actual CSE-returned AE-ID. NGINX validates the certificate, extracts that identity and rejects a conflicting X-M2M-Origin. It forwards the verified identity to the real CSE, which still executes AE/CNT/CIN/SUB and enforces ACPs. The gateway never generates successful oneM2M resources or RSC values. HTTP authentication denials at NGINX and real CSE HTTP 403/RSC 4103 denials are separate proof.

Bootstrap CAdmin and the reserved C registration identity have separate privileged certificates. Only the enrollment runner holds the CA private key; gateway/CSE/device/browser containers must not receive it. for_actor selects a new credential transport for the actual returned identity; a missing transport fails without falling back to admin. The CA is local and short-lived, with no OS trust-store change.

Only gateway and CSE join the private backend network. Ordinary test clients join the separate client network and cannot directly resolve/reach the CSE service through their declared network. No security-stack service is published on the host. This protects against application clients in that deployment; host/Docker administrators remain trusted. CA issuance/revocation infrastructure, hardware key storage and application-process isolation are not production PKI claims.

## Execute serially

~~~bash
make p1-cse-security
# Inspect the printed LOCAL_CERTIFICATE_BOUND_CSE evidence and assertions.
make cse-security-down
~~~

The command creates private .runtime/cse-mtls files and builds an isolated fire-route-security project with its own named volumes. Existing/partial/unsafe credentials are validated or rejected, never silently replaced. Cleanup preserves volumes and private evidence. OpenSSL is needed for local certificate generation/enrollment. The Python base image must also provide its OpenSSL CLI; missing tools are a failed prerequisite, not a passing crypto test.

The privileged test runner provisions eight actual AEs and their ACPs, issues certificates for their actual AE-IDs, creates a sensor CIN through mTLS, reads it as controller and receives real SUB verification/event callbacks. It verifies real resident ACP denial, sensor attempts to claim admin/controller identities, missing/untrusted client certificates and an untrusted server CA. Negative requests carry valid oneM2M headers so malformed-request rejection cannot masquerade as authentication proof. No arbitrary fixture is accepted by this actual gate.

## Explicit boundaries

- Client-to-gateway is mTLS; gateway-to-CSE and the private callback relay remain HTTP. This is not end-to-end encrypted callbacks or native ACME certificate authentication.
- The main selected demo, MQTT broker and device processes are not silently migrated by this isolated gate. Existing real Group/ACK evidence stays on its original profile; rerun the affected full scenario before claiming secure Group/device operation.
- This does not implement MQTT TLS/authentication, Mcc registrar security, application crash recovery or MEC deployment.
- nginx:1.30.6-alpine was pulled and used by the successful actual T36 run. An image digest/independent nginx -V snapshot was not retained, so those provenance fields remain unverified.

Sources: [NGINX client-certificate verification and subject variables](https://nginx.org/en/docs/http/ngx_http_ssl_module.html), [official NGINX releases](https://nginx.org/en/download.html), [ACME authentication capabilities](https://acmecse.net/setup/Certificates/). ACME Basic/Bearer support alone must not be represented as binding an arbitrary X-M2M-Origin to the authenticated actor.

Startup detail: the enrollment/listener container starts after the gateway. Its callback upstream is therefore resolved at request time rather than NGINX startup, using [Docker's documented embedded resolver](https://docs.docker.com/engine/network/#dns-services) and [NGINX variable proxy resolution](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass). The actual T36 run above now confirms startup and notification delivery for the recorded revision.

Actual observations: T36 reaches COMPLETE, all 11 runtime predicates pass and runner/gateway/CSE exit 0; the supplied terminal includes CSE shutdown completion. Original saved assertions contain ten true values and one REDACTED value because its old name included credentials. The secret filter is unchanged. The separate reviewer derives eight distinct actual AE IDs and eight valid matching public-certificate subjects/keys without reading private keys. Future runs rename that predicate to eight_actual_AEs_have_distinct_IDs; the original artifact is never rewritten. Negative TLS results are original runner assertions/source-correlated proof, not an independent packet capture.

NGINX warns about duplicate upstream Server identification headers (Werkzeug and ACME). It explicitly ignores the duplicate Server line. All 48 retained oneM2M request IDs/RSCs and the CIN CREATE/GET/SUB payload still match; no oneM2M corruption was observed. Upstream duplicate-header emission is a remaining logging issue. Warnings were not suppressed and no upstream CSE/proxy protocol behavior was changed to hide it.
