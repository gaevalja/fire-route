"""Generate an opt-in loopback development CA/cert; keys never leave .runtime.

This is not a public CA or an originator authentication implementation.
Existing credentials are validated and never silently replaced.
"""
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile


def prepare(directory=Path('.runtime/tls')):
    directory=Path(directory)
    if directory.is_symlink():raise ValueError('TLS directory must not be a symlink')
    names=('ca.key','ca.crt','server.key','server.crt')
    if directory.exists():
        if any((directory/n).is_symlink() or not (directory/n).is_file() for n in names):
            raise ValueError('Incomplete/unsafe TLS files; refusing overwrite')
        for name in ('ca.key','server.key'):
            if (directory/name).stat().st_mode&0o077:raise ValueError('TLS keys must remain private')
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(directory/'server.crt',directory/'server.key')
        subprocess.run(['openssl','verify','-CAfile',str(directory/'ca.crt'),str(directory/'server.crt')],
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
        return directory
    if not shutil.which('openssl'):raise RuntimeError('OpenSSL required for local development certificates')
    directory.parent.mkdir(parents=True,exist_ok=True)
    temporary=Path(tempfile.mkdtemp(prefix='.tls-',dir=directory.parent))
    def run(*args):
        subprocess.run(['openssl',*args],cwd=temporary,check=True,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
    try:
        run('req','-x509','-newkey','rsa:3072','-nodes','-keyout','ca.key','-out','ca.crt',
            '-sha256','-days','30','-subj','/CN=FireRoute Local Development CA',
            '-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
        run('req','-new','-newkey','rsa:2048','-nodes','-keyout','server.key','-out','server.csr',
            '-subj','/CN=localhost')
        (temporary/'extensions.cnf').write_text('subjectAltName=DNS:localhost,DNS:scenario-app,IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
        run('x509','-req','-in','server.csr','-CA','ca.crt','-CAkey','ca.key','-CAcreateserial',
            '-out','server.crt','-days','30','-sha256','-extfile','extensions.cnf')
        for name in names:os.chmod(temporary/name,0o600 if name.endswith('.key') else 0o644)
        # Private CA never enters a container; mount only its public certificate.
        for extra in ('server.csr','extensions.cnf','ca.srl'):(temporary/extra).unlink(missing_ok=True)
        temporary.rename(directory)
    finally:
        if temporary.exists():shutil.rmtree(temporary)
    return directory


if __name__=='__main__':
    try:prepare();print('Local TLS files ready in .runtime/tls; private keys are not printed.')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        raise SystemExit('TLS preparation failed; existing files were not replaced.') from None
