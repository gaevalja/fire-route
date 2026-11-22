"""Read actual configured MEC catalog; never visits an unspecified Sandbox."""
import argparse
import json
import os
from pathlib import Path

from backend.evidence import Evidence,source_identity
from backend.config import read_dotenv
from mec.catalog import CatalogSettings,discover,persist_catalog
from onem2m.client import CSEClient
from onem2m.security import MutualTLSTransport


def run(env,*,persist=False):
    evidence=Evidence(Path(env.get('EVIDENCE_ROOT','evidence')))
    summary={'test':'ACTUAL_MEC011_CATALOG','state':'NOT_RUN','MEC':'NOT_VERIFIED',
             'MEC_IPE':'NOT_IMPLEMENTED','deployment':'NOT_VERIFIED','CSE':'NOT_CONTACTED','Hosted':'NOT_CONTACTED'}
    try:
        url=env.get('MEC_SERVICE_MGMT_URL','')
        if not url:
            summary.update(state='BLOCKED',reason='MEC_SERVICE_MGMT_URL is not configured')
        else:
            settings=CatalogSettings(url,env.get('MEC_ENVIRONMENT',''),env.get('MEC_APPLICATION_INSTANCE_ID',''),
                Path(env['MEC_API_TOKEN_FILE']) if env.get('MEC_API_TOKEN_FILE') else None,
                Path(env['MEC_CA_FILE']) if env.get('MEC_CA_FILE') else None)
            # Mark the attempt before issuing transport, including failures.
            summary['Hosted']='ATTEMPTED' if settings.environment=='hosted-sandbox' else 'NOT_CONTACTED'
            snapshot=discover(settings);evidence.write('catalog.json',snapshot)
            summary.update(state='PASS',MEC='DISCOVERY_VERIFIED_ONLY',service_count=snapshot['service_count'])
            if persist:
                if not env.get('MEC_CSE_TARGET_CONTAINER'):raise ValueError('Existing scoped CSE catalog CNT required')
                tls_names=['CSE_CA_FILE','CSE_CLIENT_CERT','CSE_CLIENT_KEY']
                transport=None
                if any(env.get(k) for k in tls_names):
                    if not all(env.get(k) for k in tls_names):raise ValueError('Complete CSE TLS credentials required')
                    transport=MutualTLSTransport(*(env[k] for k in tls_names))
                client=CSEClient(env.get('CSE_BASE_URL','http://127.0.0.1:8080'),env.get('CSE_ORIGINATOR',''),
                                 env.get('CSE_RELEASE','4'),transport=transport,evidence=evidence,actor='mec-catalog-AE')
                summary['CSE']='ATTEMPTED'
                reference=persist_catalog(client,env['MEC_CSE_TARGET_CONTAINER'],snapshot)
                evidence.write('catalog-CSE.json',reference);summary['CSE']='CIN_CREATE_AND_READBACK_VERIFIED'
    except Exception as exc:
        summary.update(state='FAIL',reason=type(exc).__name__)
        status=getattr(exc,'http_status',None)
        if type(status) is int and 100<=status<=599:summary['http_status']=status
    evidence.write('meta.json',source_identity(Path(__file__).resolve().parents[1]))
    evidence.write('summary.json',summary)
    return summary,evidence.path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--persist-onem2m',action='store_true')
    args=parser.parse_args()
    values=read_dotenv(Path('.env'));values.update(os.environ)
    result,path=run(values,persist=args.persist_onem2m)
    print(json.dumps({**result,'evidence':str(path)}));raise SystemExit(0 if result['state']=='PASS' else 1)
