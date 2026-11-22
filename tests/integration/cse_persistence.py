"""Actual CSE marker creation/read-back across an externally controlled restart."""
import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

from backend.config import Settings
from backend.evidence import Evidence,source_identity
from backend.p0 import IntegrationBlocked,ROOT,wait_for_cse
from onem2m.client import CSEClient,CSEError,strict_json


def verify_marker(client,record):
    ae=client.resource(client.retrieve(record['ae_path']),2)
    if ae['ri']!=record['ae_ri'] or ae['aei']!=record['ae_id']:
        raise AssertionError('Persisted AE identity differs')
    actor=client.for_actor(ae['aei'],'persistence-marker')
    cnt=actor.resource(actor.retrieve(record['container_path']),3)
    cin=actor.resource(actor.retrieve(record['cin_path']),4)
    con=strict_json(cin['con']) if isinstance(cin['con'],str) else cin['con']
    if cnt['ri']!=record['container_ri'] or cin['ri']!=record['cin_ri'] or con!=record['content']:
        raise AssertionError('Persisted CSE resource/content differs')


def run(settings,phase,state_path):
    out=Evidence(settings.evidence_root,secret_values=(settings.admin_originator,))
    summary={'test':'CSE_PERSISTENCE_PROBE','phase':phase,'state':'NOT_RUN','MEC':'unavailable'}
    try:
        if sys.version_info<(3,11):raise IntegrationBlocked('Use the Python 3.12 stability-probe profile')
        client=CSEClient(settings.cse_url,settings.admin_originator,settings.release,
            timeout=settings.request_timeout,evidence=out)
        wait_for_cse(client,settings)
        runtime=strict_json(settings.runtime_info.read_bytes()) if settings.runtime_info else None
        if runtime is None or not runtime.get('secret_configured'):
            raise AssertionError('CSE non-default key provisioning not reported')
        shutdown_patch=runtime.get('shutdown_patch')
        if (not isinstance(shutdown_patch,dict) or shutdown_patch.get('verified') is not True
                or shutdown_patch.get('patch_id')!='acme-2026.5.1-shutdown-state-guard-v1'):
            raise AssertionError('Pinned CSE shutdown patch not verified by runtime')
        out.write('runtime-identity.json',{'installed_version':runtime.get('installed_version'),
            'config_sha256':runtime['config_sha256'],'shutdown_patch':shutdown_patch})
        if phase=='prepare':
            name='fr_restart_'+uuid4().hex[:16];path='/'+settings.cse_base+'/'+name
            ae=client.ensure('/'+settings.cse_base,2,{'rn':name,'api':'Nfire-route.restart',
                'rr':False,'srv':[settings.release],'lbl':['fire-route','namespace:'+name]},
                creator=client.for_actor('C','ae-registration'))
            actor=client.for_actor(ae['aei'],'persistence-marker')
            policy=client.ensure('/'+settings.cse_base,1,{'rn':name+'-policy',
                'lbl':['fire-route','namespace:'+name],
                'pv':{'acr':[{'acor':[ae['aei']],'acop':3},
                    {'acor':[settings.admin_originator],'acop':63}]},
                'pvs':{'acr':[{'acor':[settings.admin_originator],'acop':63}]}})
            cnt=client.ensure(path,3,{'rn':'marker','mni':2,'acpi':[policy['ri']],
                'lbl':['fire-route','namespace:'+name]})
            body={'schema_version':1,'probe_id':uuid4().hex,'data_origin':'SYNTHETIC',
                'purpose':'RESTART_PERSISTENCE_ONLY'}
            cin=actor.ensure(path+'/marker',4,{'rn':'before-restart','cnf':'application/json:0','con':json.dumps(body)})
            record={'ae_path':path,'ae_ri':ae['ri'],'ae_id':ae['aei'],'container_path':path+'/marker',
                'container_ri':cnt['ri'],'cin_path':path+'/marker/before-restart','cin_ri':cin['ri'],
                'content':body,'runtime_config_sha256':runtime['config_sha256'],
                'shutdown_patch':shutdown_patch}
            verify_marker(client,record)
            if state_path.exists():raise AssertionError('Persistence marker state already exists')
            out.write('marker.json',record)
            # The state contains only synthetic marker/returned public resource IDs.
            with state_path.open('x') as stream:json.dump(record,stream)
        elif phase=='verify':
            record=strict_json(state_path.read_bytes());verify_marker(client,record)
            if runtime['config_sha256']!=record['runtime_config_sha256']:
                raise AssertionError('CSE configuration/key changed during restart')
            if shutdown_patch!=record.get('shutdown_patch'):
                raise AssertionError('CSE shutdown patch changed during restart')
            out.write('marker.json',record)
        else:raise ValueError('Unknown persistence probe phase')
        out.write('meta.json',{'test':summary['test'],'phase':phase,'real_CSE':True,
            'cse_nondefault_key_reported':True,'config_sha256':runtime['config_sha256'],
            'shutdown_patch':shutdown_patch,**source_identity(ROOT)})
        summary.update(state='PASS',same_resource_readback=True)
    except IntegrationBlocked as exc:summary.update(state='BLOCKED',reason=str(exc))
    except CSEError as exc:
        summary.update(state='FAIL',reason=type(exc).__name__,http_status=exc.http_status,rsc=exc.rsc)
    except Exception as exc:summary.update(state='FAIL',reason=str(exc) if isinstance(exc,AssertionError) else type(exc).__name__)
    finally:out.write('summary.json',summary)
    return summary,out.path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['prepare','verify'])
    parser.add_argument('--state',required=True,type=Path);args=parser.parse_args()
    summary,path=run(Settings.load(),args.phase,args.state)
    output=json.dumps({'evidence':str(path),**summary});(path/'tests.txt').write_text(output+'\n')
    print(output);return {'PASS':0,'FAIL':1,'BLOCKED':2}[summary['state']]


if __name__=='__main__':raise SystemExit(main())
