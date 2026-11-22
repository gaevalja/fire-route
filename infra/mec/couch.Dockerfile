FROM couchdb:3.5.2.1
# The upstream entrypoint normalizes ownership before launching CouchDB.
# Keep configuration in the writable image, already owned by its native UID.
COPY --chown=5984:5984 --chmod=0644 infra/mec/couch-single.ini /opt/couchdb/etc/local.d/10-fire-route-single.ini
COPY --chown=5984:5984 --chmod=0755 infra/mec/couch_health.sh /usr/local/bin/fire-route-couch-health
