"""Probe the real upstream MEC011 HTTP endpoint; never generate a response."""
import json
import sys
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def reject_constant(value):
    raise ValueError('Invalid JSON constant')


def healthy():
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open('http://127.0.0.1/mec_service_mgmt/v1/services', timeout=3) as reply:
            body = reply.read(1024 * 1024 + 1)
            return (reply.status == 200 and reply.headers.get_content_type() == 'application/json'
                    and len(body) <= 1024 * 1024
                    and isinstance(json.loads(body, parse_constant=reject_constant), list))
    except (OSError, ValueError):
        return False


if __name__ == '__main__':
    sys.exit(0 if healthy() else 1)
