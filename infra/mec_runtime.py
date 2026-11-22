"""Stage exact reviewed official Git objects for a local MEC011 image build."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
from uuid import uuid4

from backend.evidence import Evidence, source_identity
from infra.mec_local import PreparationBlocked, prepare

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ('go-apps/meep-app-enablement', 'go-packages', 'LICENSE')


def stage_checkout(checkout, output, commit, *, prefixes=PREFIXES):
    """Use committed objects, excluding every untracked/ignored local setting."""
    try:
        archive = subprocess.check_output(['git', 'archive', '--format=tar', commit, '--', *prefixes],
                                         cwd=checkout, stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.SubprocessError):
        raise PreparationBlocked('OFFICIAL_GIT_ARCHIVE_UNAVAILABLE') from None
    expected = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            name = member.name.rstrip('/')
            allowed = any(name == p or name.startswith(p + '/') for p in prefixes)
            ancestor = member.isdir() and any(p.startswith(name + '/') for p in prefixes)
            if path.is_absolute() or '..' in path.parts or not (allowed or ancestor):
                raise PreparationBlocked('UNSAFE_RUNTIME_SOURCE_ARCHIVE')
            if member.isdir():
                continue
            if not member.isfile() or member.size > 32 * 1024 * 1024:
                raise PreparationBlocked('UNSUPPORTED_RUNTIME_SOURCE_ARCHIVE_ENTRY')
            stream = tar.extractfile(member)
            data = stream.read()
            expected[member.name] = data
    if not all(name in expected for name in ('LICENSE', 'go-apps/meep-app-enablement/main.go', 'go-apps/meep-app-enablement/go.mod')):
        raise PreparationBlocked('OFFICIAL_RUNTIME_SOURCE_INCOMPLETE')
    if output.is_symlink():
        raise PreparationBlocked('RUNTIME_BUILD_SOURCE_MUST_BE_REGULAR')
    if output.exists():
        actual = {str(p.relative_to(output)): p for p in output.rglob('*') if p.is_file() or p.is_symlink()}
        if (set(actual) != set(expected) or any(p.is_symlink() or p.read_bytes() != expected[n] for n, p in actual.items())):
            raise PreparationBlocked('STAGED_RUNTIME_SOURCE_CHANGED_NOT_OVERWRITTEN')
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name('source-' + uuid4().hex)
        temporary.mkdir()
        for name, data in expected.items():
            target = temporary / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        temporary.rename(output)
    return {name: hashlib.sha256(data).hexdigest() for name, data in expected.items()}


def stage(root=ROOT):
    source_root = root / '.runtime/mec-sandbox'
    locked = prepare(source_root, inspect_only=True)
    specification = json.loads((root / 'infra/mec/upstream.json').read_text())
    backend = locked['repositories']['etsi-mec-sandbox']
    if (backend['commit'] != specification['commit'] or backend['tree'] != specification['tree']
            or backend['url'] != specification['repository']):
        raise PreparationBlocked('REVIEWED_OFFICIAL_RUNTIME_REVISION_REQUIRED')
    hashes = stage_checkout(source_root / 'sources/etsi-mec-sandbox',
                            source_root / 'runtime-build/source', specification['commit'])
    return {'upstream': specification, 'files': hashes,
            'source_manifest_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}


def main():
    evidence = Evidence(ROOT / 'evidence')
    result = {'test': 'LOCAL_MEC_RUNTIME_SOURCE', 'state': 'NOT_RUN', 'Hosted': 'NOT_CONTACTED',
              'MEC_execution': 'NOT_PERFORMED_BY_STAGING', 'main_demo': 'NOT_CONTACTED'}
    try:
        manifest = stage()
        evidence.write('official-runtime-source.json', manifest)
        result.update(state='SOURCE_STAGED', commit=manifest['upstream']['commit'], files=len(manifest['files']))
    except PreparationBlocked as exc:
        result.update(state='BLOCKED', reason=str(exc))
    except (OSError, ValueError, KeyError):
        result.update(state='FAIL', reason='RUNTIME_SOURCE_STAGING_FAILED')
    evidence.write('meta.json', source_identity(ROOT))
    evidence.write('summary.json', result)
    print(json.dumps({**result, 'evidence': str(evidence.path)}))
    return 0 if result['state'] == 'SOURCE_STAGED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
