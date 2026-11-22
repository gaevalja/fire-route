"""Narrow, hash-pinned workaround for the observed ACME shutdown-state guard.

Installed source was collected in evidence/20261114-050745Z-321ec6ce/.
No oneM2M behavior, storage format or database settings are replaced.
"""
import ast
import hashlib
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import stat
import tempfile

VERSION='2026.5.1'
SOURCE='acmecse/runtime/CSE.py'
SOURCE_SHA256='5b8678ba45450090befef0d183faad429724478122f4f910f368d2a44d83e7ae'
PATCH_ID='acme-2026.5.1-shutdown-state-guard-v1'
MANIFEST=Path('/opt/fire-route/cse-shutdown-patch.json')


def patch_source(body: bytes) -> bytes:
    """Preserve upstream bytes except one extra accepted shutdown state."""
    if hashlib.sha256(body).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Unsupported ACME source hash; refusing patch')
    tree=ast.parse(body)
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_shutdown']
    if len(functions)!=1:raise ValueError('Unexpected ACME shutdown function')
    function=functions[0]
    if not any(ast.dump(d)==ast.dump(ast.parse('atexit.register',mode='eval').body)
               for d in function.decorator_list):
        raise ValueError('Unexpected ACME exit handler')
    statements=[s for s in function.body if not (isinstance(s,ast.Expr)
        and isinstance(s.value,ast.Constant) and isinstance(s.value.value,str))]
    guard=statements[0] if statements else None
    expected=ast.parse('RC.cseStatus not in [CSEStatus.RUNNING, CSEStatus.SHUTTINGDOWNRESTART]',mode='eval').body
    if (not isinstance(guard,ast.If) or ast.dump(guard.test)!=ast.dump(expected)
            or guard.orelse or len(guard.body)!=1 or not isinstance(guard.body[0],ast.Return)
            or guard.body[0].value is not None):
        raise ValueError('Unexpected ACME shutdown guard')
    states=guard.test.comparators[0]
    lines=body.splitlines(keepends=True)
    position=sum(map(len,lines[:states.lineno-1]))+states.col_offset+1
    if body[position-1:position]!=b'[':raise ValueError('Unexpected source offset')
    patched=body[:position]+b'CSEStatus.SHUTTINGDOWN, '+body[position:]
    compile(patched,SOURCE,'exec')
    return patched


def installed_source():
    package=distribution('acmecse')
    if package.version!=VERSION:raise ValueError('Unsupported ACME version; refusing patch')
    root=Path(package.locate_file('acmecse')).resolve()
    path=Path(package.locate_file(SOURCE)).resolve()
    if not path.is_relative_to(root):raise ValueError('Unexpected installed source path')
    return path


def verify_installed_patch(manifest: Path=MANIFEST) -> dict:
    record=json.loads(manifest.read_text())
    if (not isinstance(record,dict) or record.get('patch_id')!=PATCH_ID or record.get('installed_version')!=VERSION
            or record.get('source')!=SOURCE or record.get('upstream_sha256')!=SOURCE_SHA256):
        raise ValueError('Invalid CSE shutdown patch manifest')
    body=installed_source().read_bytes()
    if hashlib.sha256(body).hexdigest()!=record.get('patched_sha256'):
        raise ValueError('CSE shutdown patch verification failed')
    # Reverse exactly this insertion and re-check the pinned original, so a
    # manifest cannot authorize unrelated source changes.
    insertion=b'CSEStatus.SHUTTINGDOWN, '
    candidates=[i for i in range(len(body)) if body.startswith(insertion,i)]
    if not any(hashlib.sha256(body[:i]+body[i+len(insertion):]).hexdigest()==SOURCE_SHA256
               for i in candidates):
        raise ValueError('CSE patch does not match pinned source')
    return {**record,'verified':True}


def main():
    try:
        path=installed_source();body=path.read_bytes();patched=patch_source(body)
        mode=stat.S_IMODE(path.stat().st_mode)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.fire-route-shutdown-',delete=False) as stream:
                temporary=Path(stream.name);stream.write(patched);stream.flush();os.fsync(stream.fileno())
            temporary.chmod(mode);temporary.replace(path);temporary=None
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
        record={'patch_id':PATCH_ID,'installed_version':VERSION,'source':SOURCE,
            'upstream_sha256':SOURCE_SHA256,'patched_sha256':hashlib.sha256(patched).hexdigest()}
        MANIFEST.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
        verified=verify_installed_patch(MANIFEST)
        print(json.dumps({'phase':'CSE_SHUTDOWN_PATCH','state':'APPLIED',**verified}));return 0
    except (OSError,ValueError,SyntaxError):
        print(json.dumps({'phase':'CSE_SHUTDOWN_PATCH','state':'FAIL',
            'reason':'Pinned CSE shutdown patch could not be applied/verified'}));return 1


if __name__=='__main__':raise SystemExit(main())
