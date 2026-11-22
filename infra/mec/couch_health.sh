#!/bin/bash
# Bash ships with the upstream entrypoint; curl is not required for this probe.
set -euo pipefail

couch_read_status() {
    local couch_http_status
    IFS= read -r -t 2 couch_http_status <&3 || return 1
    [[ "$couch_http_status" == 'HTTP/1.1 200 '* ]]
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    exec 3<>/dev/tcp/127.0.0.1/5984
    printf 'GET /_up HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n' >&3
    couch_read_status
fi
