"""Prepare reviewed controller Git objects and private local service configuration."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat

from backend.evidence import Evidence, source_identity
from infra.mec_runtime import ROOT, stage, stage_checkout


def private_environment(path, *, kind='couch'):
    if path.is_symlink():
        raise ValueError('Private local configuration must be a regular owned file')
    if path.exists():
        mode = path.stat()
        if not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid() or mode.st_mode & 0o077:
            raise ValueError('Private local configuration must be owned and mode 0600')
        from backend.config import read_dotenv
        data = read_dotenv(path)
        fields={'COUCHDB_USER','COUCHDB_PASSWORD'} if kind=='couch' else {'FR_RISK_ACCESS_KEY'}
        if set(data) != fields or any(not v for v in data.values()):
            raise ValueError('Private local configuration is incomplete')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    content = ('COUCHDB_USER=fire-route\nCOUCHDB_PASSWORD=' + secrets.token_hex(32) + '\n'
               if kind=='couch' else 'FR_RISK_ACCESS_KEY=' + secrets.token_hex(32) + '\n')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)


def prepare(root=ROOT):
    previous = stage(root)
    official = root / '.runtime/mec-sandbox'
    prefixes = ('go-apps/meep-app-enablement', 'go-apps/meep-sandbox-ctrl', 'go-packages', 'LICENSE')
    hashes = stage_checkout(official/'sources/etsi-mec-sandbox', official/'services-build/source',
                            previous['upstream']['commit'], prefixes=prefixes)
    private_environment(root/'.runtime/mec-couch.env')
    private_environment(root/'.runtime/mec-risk.env',kind='risk')
    return {'upstream': previous['upstream'], 'files': hashes,
            'source_manifest_sha256': hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
            'build_copy_patch':'Couch auth only; official checkout and existing runtime are unchanged'}


def main():
    ev = Evidence(ROOT/'evidence')
    result = {'test':'LOCAL_MEC_SERVICES_PREPARE','Hosted':'NOT_CONTACTED','runtime':'NOT_EXECUTED'}
    try:
        manifest = prepare()
        ev.write('official-services-source.json',manifest)
        result.update(state='PREPARED',files=len(manifest['files']))
    except Exception as exc:
        result.update(state='BLOCKED',reason=type(exc).__name__)
    ev.write('meta.json',source_identity(ROOT));ev.write('summary.json',result)
    print(json.dumps({**result,'evidence':str(ev.path)}))
    return 0 if result['state']=='PREPARED' else 1


if __name__=='__main__':raise SystemExit(main())
