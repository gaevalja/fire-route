"""Verified TLS transport; originator binding is enforced by the mTLS gateway.

This is transport security in front of the real CSE, not a CSE implementation.
"""
from pathlib import Path
import ssl
from urllib.parse import urlsplit

from onem2m.client import HTTPTransport, TransportError


class MutualTLSTransport(HTTPTransport):
    def __init__(self, ca, certificate, key):
        paths=[Path(p) for p in (ca,certificate,key)]
        if any(p.is_symlink() or not p.is_file() for p in paths):
            raise ValueError('Missing or unsafe CSE TLS files')
        if paths[2].stat().st_mode & 0o077:
            raise ValueError('CSE client key must remain private')
        try:
            context=ssl.create_default_context(cafile=str(paths[0]))
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(paths[1]),str(paths[2]))
        except (ssl.SSLError,OSError):
            raise ValueError('Invalid CSE TLS credentials') from None
        super().__init__(tls_context=context)

    def __call__(self, method, url, headers, body, timeout):
        if urlsplit(url).scheme!='https':
            raise TransportError('Authenticated CSE transport requires HTTPS')
        return super().__call__(method,url,headers,body,timeout)
