"""Local authenticated FireRoute API + same-origin static dashboard."""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from backend.views import unknown_view
from onem2m.client import CSEError,strict_json

COOKIE='fr_session'
STATIC={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),
        '/model.mjs':('model.mjs','text/javascript; charset=utf-8'),'/styles.css':('styles.css','text/css; charset=utf-8')}


def api_server(host,port,app,auth,origin,static_root:Path,*,actions=None,snapshots=False):
    allowed_actions = frozenset(actions if actions is not None else {'fire_a','fire_b','stop_display_c','reset','pause','resume'})
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass

        def token(self):
            cookie=SimpleCookie()
            try:cookie.load(self.headers.get('Cookie',''))
            except Exception:return ''
            return cookie[COOKIE].value if COOKIE in cookie else ''

        def send(self,status,body,*,media='application/json',cookie=None):
            data=json.dumps(body,allow_nan=False).encode() if media=='application/json' else body
            self.send_response(status)
            for name,value in [('Content-Type',media),('Content-Length',str(len(data))),('Cache-Control','no-store'),
                ('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),
                ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]:
                self.send_header(name,value)
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(data)
            app.audit(self.command,urlsplit(self.path).path,status,auth.role(self.token()))

        def session_cookie(self,token,*,clear=False):
            value=f'{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else auth.lifetime}'
            return value+('; Secure' if origin.startswith('https://') else '')

        def do_GET(self):
            path=urlsplit(self.path).path
            if path=='/healthz':return self.send(200,{'state':'RUNNING'})
            if self.headers.get('Host')!=urlsplit(origin).netloc:return self.send(421,{'error':'INVALID_HOST'})
            if self.path!=path:return self.send(400,{'error':'QUERY_NOT_SUPPORTED'})
            if path in STATIC:
                name,media=STATIC[path]
                return self.send(200,(static_root/name).read_bytes(),media=media)
            role=auth.role(self.token())
            if not role:return self.send(401,{'error':'AUTH_REQUIRED'})
            if path=='/api/v1/session':return self.send(200,{'role':role})
            if path=='/api/v1/status':return self.send(200,app.status())
            if path=='/api/v1/building':return self.send(200,app.building)
            parts=path.split('/')
            endpoints={'resident','responder'}|({'snapshot'} if snapshots else set())
            if len(parts)!=6 or parts[1:4]!=['api','v1','incidents'] or parts[5] not in endpoints:
                return self.send(404,{'error':'NOT_FOUND'})
            if parts[5] in {'responder','snapshot'} and role!='responder':return self.send(403,{'error':'ROLE_DENIED'})
            try:
                result=app.snapshot(parts[4],role) if parts[5]=='snapshot' else app.view(parts[4],role,diagnostics=parts[5]=='responder')
                return self.send(200,result)
            except LookupError:return self.send(404,{'error':'INCIDENT_NOT_FOUND'})
            except (CSEError,ValueError,KeyError,TypeError):
                return self.send(503,unknown_view(parts[4]))

        def json_body(self):
            if self.headers.get('Host')!=urlsplit(origin).netloc or self.headers.get('Origin')!=origin:
                self.send(403,{'error':'ORIGIN_DENIED'});return None
            if self.headers.get('Content-Type','').split(';')[0]!='application/json' or self.headers.get('Transfer-Encoding'):
                self.send(415,{'error':'JSON_REQUIRED'});return None
            try:
                size=int(self.headers.get('Content-Length',''))
                if not 0<size<=4096:raise ValueError()
                self.connection.settimeout(5)
                data=self.rfile.read(size)
                if len(data)!=size:raise ValueError()
                body=strict_json(data)
                if not isinstance(body,dict):raise ValueError()
                return body
            except (ValueError,OSError):self.send(400,{'error':'INVALID_BODY'});return None

        def do_POST(self):
            body=self.json_body()
            if body is None:return
            if self.path=='/api/v1/session':
                if set(body)!={'role','access_code'}:return self.send(400,{'error':'INVALID_FIELDS'})
                token,state=auth.login(body['role'],body['access_code'],self.client_address[0])
                if not token:return self.send(429 if state=='RATE_LIMITED' else 401,{'error':state})
                return self.send(200,{'role':body['role']},cookie=self.session_cookie(token))
            if self.path!='/api/v1/scenario':return self.send(404,{'error':'NOT_FOUND'})
            role=auth.role(self.token())
            if not role:return self.send(401,{'error':'AUTH_REQUIRED'})
            if role!='responder':return self.send(403,{'error':'ROLE_DENIED'})
            if set(body)!={'action'} or not isinstance(body['action'],str) or body['action'] not in allowed_actions:
                return self.send(400,{'error':'INVALID_ACTION'})
            try:job=app.enqueue(body['action'])
            except RuntimeError:return self.send(409,{'error':'SCENARIO_BUSY'})
            return self.send(202,{'job_id':job,'state':'QUEUED'})

        def do_DELETE(self):
            if self.path!='/api/v1/session':return self.send(404,{'error':'NOT_FOUND'})
            if self.headers.get('Origin')!=origin or self.headers.get('Host')!=urlsplit(origin).netloc:
                return self.send(403,{'error':'ORIGIN_DENIED'})
            auth.logout(self.token())
            return self.send(200,{'state':'SIGNED_OUT'},cookie=self.session_cookie('',clear=True))
    server=ThreadingHTTPServer((host,port),Handler)
    server.daemon_threads=True
    return server
