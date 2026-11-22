"""Read installed ACME lifecycle/storage source without importing or stopping CSE."""
import inspect
import json
from pathlib import Path
import re
import subprocess

from backend.evidence import Evidence,source_identity
from infra.cse.diagnostics import DockerUnavailable,command


def snapshot_sources():
    # This self-contained function is sent on stdin to the existing container.
    # Inspect only installed package code, never config, environment or DB files.
    import ast
    import hashlib
    from importlib.metadata import distribution
    from pathlib import Path

    class HideLiterals(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,(str,bytes)):
                return ast.copy_location(ast.Constant('[REDACTED_LITERAL]'),node)
            return node

    package=distribution('acmecse');root=Path(package.locate_file('acmecse')).resolve()
    records=[];total=0
    for item in sorted(package.files or [],key=str):
        name=str(item);path=Path(name)
        if not name.startswith('acmecse/') or path.suffix!='.py':continue
        if not (name in {'acmecse/__main__.py','acmecse/__init__.py','acmecse/runtime/CSE.py',
                          'acmecse/runtime/Storage.py','acmecse/helpers/KeyHandler.py'}
                or 'tinydb' in name.lower() or 'console' in name.lower()):continue
        actual=Path(package.locate_file(item)).resolve()
        if not actual.is_relative_to(root):raise ValueError('Package source path outside package')
        if len(records)>=24 or actual.stat().st_size>256*1024:
            raise ValueError('Installed source exceeds audit limits')
        body=actual.read_bytes();total+=len(body)
        if total>1024*1024:raise ValueError('Installed source exceeds audit limits')
        tree=ast.parse(body);safe=HideLiterals().visit(tree)
        records.append({'path':name,'sha256':hashlib.sha256(body).hexdigest(),
            'sanitized_source':ast.unparse(safe)})
    if not records:raise ValueError('Installed lifecycle sources unavailable')
    return {'implementation':'ACME','installed_version':package.version,'files':records,
        'scope':'STATIC_INSTALLED_SOURCE_NOT_RUNTIME_OR_DURABILITY_PROOF',
        'literals':'ALL_STRING_AND_BYTE_LITERALS_REDACTED',
        'runtime_config_env_DB':'NOT_READ'}


def main():
    out=Evidence(Path('evidence'));summary={'test':'CSE_INSTALLED_RUNTIME_AUDIT',
        'state':'NOT_RUN','CSE_lifecycle':'NOT_CHANGED','Hosted':'NOT_CONTACTED'}
    try:
        cid=command(['docker','compose','ps','--quiet','cse']).strip()
        if not re.fullmatch(r'[0-9a-f]{12,64}',cid):
            raise DockerUnavailable('No unique running local CSE')
        script='import json\n'+inspect.getsource(snapshot_sources)+'\nprint(json.dumps(snapshot_sources()))\n'
        result=subprocess.run(['docker','exec','-i',cid,'python','-'],input=script,
            capture_output=True,text=True,timeout=30)
        if result.returncode or len(result.stdout)>2*1024*1024:
            raise DockerUnavailable('Installed package source inspection unavailable')
        data=json.loads(result.stdout)
        if not isinstance(data.get('files'),list) or not data['files']:
            raise ValueError('No installed source records')
        out.write('installed-runtime-source.json',data)
        summary.update(state='PASS',installed_version=data['installed_version'],source_files=len(data['files']),
            scope='SOURCE_COLLECTION_ONLY_NOT_LIFECYCLE_PASS')
    except (DockerUnavailable,OSError,ValueError,KeyError,subprocess.TimeoutExpired):
        summary.update(state='BLOCKED',reason='Installed CSE source collection unavailable')
    out.write('meta.json',{'test':summary['test'],**source_identity(Path(__file__).resolve().parents[2])})
    out.write('summary.json',summary);print(json.dumps({'evidence':str(out.path),**summary}))
    return 0 if summary['state']=='PASS' else 2


if __name__=='__main__':raise SystemExit(main())
