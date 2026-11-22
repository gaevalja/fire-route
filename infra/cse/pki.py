"""Private local test CA; issue credentials only for observed/authorized AE IDs.

Only the privileged enrollment runner owns the CA key. It must never be mounted
into the gateway, CSE, resident browser, or ordinary device containers.
"""
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile


def run(*args,cwd):
    try:
        subprocess.run(['openssl',*args],cwd=cwd,check=True,timeout=30,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except (OSError,subprocess.SubprocessError):
        raise RuntimeError('Local CSE certificate operation failed') from None


def safe_directory(path):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise ValueError('Certificate symlink path rejected')
    return path


def validate(directory,names):
    directory=safe_directory(directory)
    for name in names:
        p=directory/name
        if p.is_symlink() or not p.is_file():raise ValueError('Incomplete CSE certificate files')
        if name.endswith('.key') and p.stat().st_mode & 0o077:
            raise ValueError('CSE private key permissions rejected')


def prepare(directory=Path('.runtime/cse-mtls')):
    directory=safe_directory(directory).absolute()
    names=('ca.key','ca.crt')
    if directory.exists():
        validate(directory,names)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(directory/'ca.crt',directory/'ca.key')
        run('verify','-CAfile',str(directory/'ca.crt'),str(directory/'ca.crt'),cwd=directory)
        return directory
    directory.parent.mkdir(parents=True,exist_ok=True)
    temp=Path(tempfile.mkdtemp(prefix='.cse-ca-',dir=directory.parent))
    try:
        run('req','-x509','-newkey','rsa:3072','-nodes','-keyout','ca.key','-out','ca.crt',
            '-days','30','-sha256','-subj','/CN=FireRoute Isolated CSE CA',
            '-addext','basicConstraints=critical,CA:TRUE',
            '-addext','keyUsage=critical,keyCertSign,cRLSign',cwd=temp)
        os.chmod(temp/'ca.key',0o600);os.chmod(temp/'ca.crt',0o644)
        temp.rename(directory)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return directory


def issue(directory,originator,*,server=False):
    directory=safe_directory(directory).absolute()
    if not isinstance(originator,str) or not re.fullmatch(r'C[A-Za-z0-9_-]{0,127}',originator):
        raise ValueError('Unsupported certificate-bound AE identity')
    validate(directory,('ca.key','ca.crt'))
    target=directory/('gateway' if server else originator)
    safe_directory(target)
    if target.exists():
        validate(target,('certificate.crt','private.key'))
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(target/'certificate.crt',target/'private.key')
        run('verify','-purpose','sslserver' if server else 'sslclient','-CAfile',str(directory/'ca.crt'),
            str(target/'certificate.crt'),cwd=directory)
        # Reject a valid chain with a different stored identity; no silent reissue.
        output=subprocess.run(['openssl','x509','-in',str(target/'certificate.crt'),'-noout','-subject','-nameopt','RFC2253'],
                              check=True,capture_output=True,text=True,timeout=10).stdout.strip()
        if output!='subject=CN='+originator:raise ValueError('Existing certificate identity mismatch')
        return target
    temp=Path(tempfile.mkdtemp(prefix='.issue-',dir=directory))
    try:
        run('req','-new','-newkey','rsa:2048','-nodes','-keyout','private.key','-out','request.csr',
            '-subj','/CN='+originator,cwd=temp)
        extensions='basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n'
        extensions+='extendedKeyUsage='+('serverAuth' if server else 'clientAuth')+'\n'
        if server:extensions+='subjectAltName=DNS:gateway,DNS:localhost,IP:127.0.0.1\n'
        (temp/'extensions.cnf').write_text(extensions)
        run('x509','-req','-in','request.csr','-CA',str(directory/'ca.crt'),'-CAkey',str(directory/'ca.key'),
            '-set_serial',str(int.from_bytes(os.urandom(20),'big')>>1),'-out','certificate.crt',
            '-days','7','-sha256','-extfile','extensions.cnf',cwd=temp)
        os.chmod(temp/'private.key',0o600);os.chmod(temp/'certificate.crt',0o644)
        (temp/'request.csr').unlink();(temp/'extensions.cnf').unlink()
        temp.rename(target)
    finally:
        if temp.exists():shutil.rmtree(temp)
    return target


if __name__=='__main__':
    try:
        ca=prepare();issue(ca,'CAdmin');issue(ca,'Cgateway',server=True)
        print('Private CSE mTLS files prepared; no keys printed.')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        raise SystemExit('CSE PKI preparation failed; existing credentials were not replaced.') from None
