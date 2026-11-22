"""Actual HTTPS certificate validation + role session checks, no mock service."""
import http.client
import json
import os
from pathlib import Path
import ssl
import sys

from backend.evidence import Evidence


def main():
    evidence=Evidence(Path('evidence'))
    summary={'test':'LOCAL_HTTPS','state':'NOT_RUN','Hosted':'NOT_CONTACTED',
        'MEC':'unavailable','scope':'BROWSER_API_TLS_ONLY_NOT_CSE_ORIGINATOR_AUTHENTICATION'}
    checks={};connection=None
    try:
        port=int(os.getenv('SECURE_HOST_PORT','3443'))
        if not 1024<=port<=65535:raise ValueError('Invalid loopback HTTPS port')
        context=ssl.create_default_context(cafile='.runtime/tls/ca.crt')
        connection=http.client.HTTPSConnection('127.0.0.1',port,context=context,timeout=5)
        connection.connect()
        checks['trusted_local_CA_and_hostname_verified']=True
        checks['TLS12_or_newer']=connection.sock.version() in {'TLSv1.2','TLSv1.3'}
        summary['TLS_version']=connection.sock.version()
        summary['cipher']=connection.sock.cipher()[0]
        connection.request('GET','/api/v1/status');response=connection.getresponse();response.read()
        checks['anonymous_private_API_401']=response.status==401
        connection.close()
        try:
            untrusted=http.client.HTTPSConnection('127.0.0.1',port,context=ssl.create_default_context(),timeout=5)
            try:untrusted.connect();checks['untrusted_CA_rejected']=False
            finally:untrusted.close()
        except ssl.SSLCertVerificationError:checks['untrusted_CA_rejected']=True
        for role in ('resident','responder'):
            codes=json.loads(Path('.runtime/access-codes.json').read_text())
            connection=http.client.HTTPSConnection('127.0.0.1',port,context=context,timeout=5)
            connection.request('POST','/api/v1/session',json.dumps({'role':role,'access_code':codes[role]}),
                {'Origin':f'https://127.0.0.1:{port}','Content-Type':'application/json'})
            response=connection.getresponse();body=json.loads(response.read());cookie=response.getheader('Set-Cookie','')
            checks[role+'_HTTPS_login_and_secure_cookie']=(response.status==200 and body.get('role')==role
                and all(flag in cookie for flag in ('HttpOnly','SameSite=Strict','Secure')))
            checks[role+'_CSP_present']="frame-ancestors 'none'" in response.getheader('Content-Security-Policy','')
            connection.close()
        summary['state']='PASS' if all(checks.values()) else 'FAIL'
    except (PermissionError,ConnectionRefusedError,FileNotFoundError):
        summary.update(state='BLOCKED',reason='Local HTTPS endpoint/certificates unavailable or socket access denied')
    except (OSError,ValueError,http.client.HTTPException) as exc:
        summary.update(state='FAIL',reason=type(exc).__name__)
    finally:
        if connection:connection.close()
        evidence.write('assertions.json',checks);summary['checks']=len(checks)
        evidence.write('summary.json',summary)
    print(json.dumps({**summary,'evidence':str(evidence.path)},sort_keys=True))
    return 0 if summary['state']=='PASS' else 1

if __name__=='__main__':sys.exit(main())
