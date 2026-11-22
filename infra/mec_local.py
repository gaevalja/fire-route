"""Acquire/audit official local Sandbox sources; never install an invented MEC."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from uuid import uuid4

from backend.evidence import Evidence, source_identity

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {
    'etsi-mec-sandbox': 'https://labs.etsi.org/rep/mec/etsi-mec-sandbox.git',
    'etsi-mec-sandbox-frontend': 'https://labs.etsi.org/rep/mec/etsi-mec-sandbox-frontend.git',
}
BRANCH = 'STF_685'


class PreparationBlocked(RuntimeError):
    pass


def git(directory, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_ASKPASS='/bin/false')
    command = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false',
               '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never', *args]
    try:
        result = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                                timeout=120, text=True)
    except (OSError, subprocess.TimeoutExpired):
        raise PreparationBlocked('GIT_UNAVAILABLE_OR_TIMEOUT') from None
    if result.returncode:
        # Do not expose helper/proxy output that might contain local credentials.
        reason = 'GIT_OPERATION_FAILED'
        if 'Could not resolve host' in result.stderr:
            reason = 'ETSI_DNS_UNAVAILABLE'
        elif any(x in result.stderr.lower() for x in ['authentication failed', 'could not read username', 'access denied']):
            reason = 'ETSI_REPOSITORY_ACCESS_UNAVAILABLE'
        raise PreparationBlocked(reason)
    return result.stdout


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def audit_repository(path, repository, expected=None):
    if repository not in REPOSITORIES or path.is_symlink() or not (path / '.git').is_dir():
        raise PreparationBlocked('OFFICIAL_SOURCE_CHECKOUT_REQUIRED')
    if git(path, 'remote', 'get-url', 'origin').strip() != REPOSITORIES[repository]:
        raise PreparationBlocked('OFFICIAL_SOURCE_REMOTE_MISMATCH')
    commit = git(path, 'rev-parse', '--verify', 'HEAD^{commit}').strip()
    branch_commit = git(path, 'rev-parse', '--verify', 'refs/remotes/origin/' + BRANCH + '^{commit}').strip()
    if not re.fullmatch('[0-9a-f]{40}', commit) or commit != branch_commit:
        raise PreparationBlocked('SOURCE_BRANCH_OR_COMMIT_MISMATCH')
    if git(path, 'status', '--porcelain', '--untracked-files=all').strip():
        raise PreparationBlocked('SOURCE_HAS_LOCAL_CHANGES_NOT_OVERWRITTEN')
    tree = git(path, 'rev-parse', '--verify', 'HEAD^{tree}').strip()
    files = git(path, 'ls-files', '-z').split('\0')
    selected = {}
    for name in filter(None, files):
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise PreparationBlocked('UNSAFE_SOURCE_PATH')
        candidate = path / name
        if (name.startswith(('deploy/', 'playbooks/')) or name in {'README.md', 'LICENSE', 'LICENSE.md'}):
            # A link is reported as a link, never followed into another checkout.
            if candidate.is_symlink():
                selected[name] = {'kind': 'SYMLINK_NOT_READ'}
            elif candidate.is_file():
                selected[name] = {'sha256': hashlib.sha256(candidate.read_bytes()).hexdigest()}
    result = {'url': REPOSITORIES[repository], 'branch': BRANCH, 'commit': commit,
              'tree': tree, 'tracked_files': len(list(filter(None, files))), 'review_files': selected}
    if expected is not None and result != expected:
        raise PreparationBlocked('LOCKED_SOURCE_CHANGED_NOT_OVERWRITTEN')
    return result


def prepare(directory, *, inspect_only=False, progress=None):
    directory = Path(directory)
    if directory.is_symlink():
        raise PreparationBlocked('SOURCE_DIRECTORY_MUST_BE_REGULAR')
    if not inspect_only:
        directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / 'sources.lock.json'
    if lock_path.is_symlink():
        raise PreparationBlocked('SOURCE_LOCK_MUST_BE_REGULAR')
    if lock_path.exists():
        try:
            locked = json.loads(lock_path.read_text())
            if locked['schema_version'] != 1 or not isinstance(locked['repositories'], dict):
                raise ValueError()
        except (ValueError, KeyError, TypeError, OSError):
            raise PreparationBlocked('INVALID_SOURCE_LOCK') from None
    else:
        locked = {'schema_version': 1, 'repositories': {}}
    if set(locked['repositories']) - set(REPOSITORIES):
        raise PreparationBlocked('UNEXPECTED_SOURCE_LOCK_ENTRY')
    if any(not isinstance(v, dict) or v.get('url') != REPOSITORIES[k] or v.get('branch') != BRANCH
           or not isinstance(v.get('commit'), str) or not re.fullmatch('[0-9a-f]{40}', v['commit'])
           for k, v in locked['repositories'].items()):
        raise PreparationBlocked('INVALID_SOURCE_LOCK')
    sources = directory / 'sources'
    if sources.is_symlink():
        raise PreparationBlocked('SOURCE_DIRECTORY_MUST_BE_REGULAR')
    if not inspect_only:
        sources.mkdir(exist_ok=True)
    for name, url in REPOSITORIES.items():
        if progress:
            progress(name)
        target = sources / name
        expected = locked['repositories'].get(name)
        if target.exists():
            if expected is None:
                raise PreparationBlocked('UNOWNED_SOURCE_DIRECTORY_NOT_OVERWRITTEN')
            result = audit_repository(target, name, expected)
        elif inspect_only or expected is not None:
            raise PreparationBlocked('LOCKED_OFFICIAL_SOURCE_MISSING')
        else:
            # Failed downloads are retained separately; the final target stays reusable.
            downloads = directory / 'downloads'
            if downloads.is_symlink():
                raise PreparationBlocked('SOURCE_DIRECTORY_MUST_BE_REGULAR')
            downloads.mkdir(exist_ok=True)
            temporary = downloads / (name + '-' + uuid4().hex[:12])
            git(directory, 'clone', '--depth=1', '--single-branch', '--branch', BRANCH,
                '--', url, str(temporary.resolve()))
            result = audit_repository(temporary, name)
            temporary.rename(target)
            locked['repositories'][name] = result
            atomic_json(lock_path, locked)
    return locked


def run(directory, *, inspect_only=False, evidence_root=None):
    evidence = Evidence(Path(evidence_root or ROOT / 'evidence'))
    result = {'test': 'LOCAL_MEC_OFFICIAL_SOURCE', 'state': 'NOT_RUN', 'Hosted': 'NOT_CONTACTED',
              'MEC_platform': 'NOT_INSTALLED_BY_THIS_COMMAND', 'source_scripts': 'NOT_EXECUTED',
              'main_demo': 'NOT_CONTACTED', 'video': 'OUT_OF_SCOPE'}
    try:
        snapshot = prepare(directory, inspect_only=inspect_only,
                           progress=lambda name: print(json.dumps({'test': result['test'], 'phase': 'VERIFY' if inspect_only else 'ACQUIRE_OR_VERIFY', 'repository': name}), flush=True))
        evidence.write('source-audit.json', snapshot)
        result.update(state='SOURCE_READY_FOR_REVIEW', repositories=len(snapshot['repositories']))
    except PreparationBlocked as exc:
        result.update(state='BLOCKED', reason=str(exc))
    except (OSError, ValueError, TypeError):
        result.update(state='FAIL', reason='SOURCE_FILESYSTEM_OR_FORMAT_ERROR')
    evidence.write('meta.json', source_identity(ROOT))
    evidence.write('summary.json', result)
    return result, evidence.path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    args = parser.parse_args()
    result, path = run(ROOT / '.runtime/mec-sandbox', inspect_only=args.inspect)
    print(json.dumps({**result, 'evidence': str(path)}))
    return 0 if result['state'] == 'SOURCE_READY_FOR_REVIEW' else 1


if __name__ == '__main__':
    raise SystemExit(main())
