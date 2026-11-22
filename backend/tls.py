"""Optional native HTTPS for the local dashboard; no verification bypass."""
from pathlib import Path
import ssl
from urllib.parse import urlsplit


def server_context(origin, certificate=None, key=None):
    scheme=urlsplit(origin).scheme
    if scheme not in {'http','https'}:raise ValueError('HTTP(S) public origin required')
    if not certificate and not key:
        if scheme=='https':raise ValueError('HTTPS origin requires certificate and private key')
        return None
    if not certificate or not key or scheme!='https':
        raise ValueError('TLS requires HTTPS origin and both certificate/key files')
    cert,key_path=Path(certificate),Path(key)
    if cert.is_symlink() or key_path.is_symlink():raise ValueError('TLS symlink files rejected')
    if key_path.exists() and key_path.stat().st_mode&0o077:
        raise ValueError('TLS private key must not be readable by other users')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    try:context.load_cert_chain(certfile=str(cert),keyfile=str(key_path))
    except (OSError,ssl.SSLError):raise ValueError('TLS certificate/key unavailable or invalid') from None
    return context
