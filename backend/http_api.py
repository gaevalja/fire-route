"""Local authenticated FireRoute API + same-origin static dashboard."""
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit

from backend.model_replay import COMPARE_PATH, MAKER_PREFIX, REPLAY_PAGE, REPLAY_PREFIX
from backend.views import unknown_view
from onem2m.client import CSEError,strict_json

COOKIE='fr_session'
STATIC={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),
        '/model.mjs':('model.mjs','text/javascript; charset=utf-8'),'/styles.css':('styles.css','text/css; charset=utf-8'),
        '/locale.js':('locale.js','text/javascript; charset=utf-8'),
        # WebGL building view and evacuation timeline; present only in the selected scenario dashboard.
        '/building-view.mjs':('building-view.mjs','text/javascript; charset=utf-8'),
        '/timeline.mjs':('timeline.mjs','text/javascript; charset=utf-8')}


def api_server(host,port,app,auth,origin,static_root:Path,*,actions=None,snapshots=False,tls_context=None,model_replay=None):
    allowed_actions = frozenset(actions if actions is not None else {'fire_a','fire_b','stop_display_c','reset','pause','resume'})
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self,*args):pass

        def token(self):
            cookie=SimpleCookie()
            try:cookie.load(self.headers.get('Cookie',''))
            except Exception:return ''
            return cookie[COOKIE].value if COOKIE in cookie else ''

        def send(self,status,body,*,media='application/json',cookie=None,embeddable=False):
            data=json.dumps(body,allow_nan=False).encode() if media=='application/json' else body
            self.send_response(status)
            frame_ancestors = "'self'" if embeddable else "'none'"
            for name,value in [('Content-Type',media),('Content-Length',str(len(data))),('Cache-Control','no-store'),
                ('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),
                ('Content-Security-Policy',f"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors {frame_ancestors}; base-uri 'none'; form-action 'self'")]:
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
                if not (static_root/name).is_file():return self.send(404,{'error':'NOT_FOUND'})
                return self.send(200,(static_root/name).read_bytes(),media=media)
            role=auth.role(self.token())
            if not role:return self.send(401,{'error':'AUTH_REQUIRED'})
            if model_replay is not None and path.startswith((REPLAY_PREFIX, MAKER_PREFIX)):
                if role!='responder':return self.send(403,{'error':'ROLE_DENIED'})
                if path==REPLAY_PREFIX+'runs':return self.send(200,model_replay.catalog())
                asset=model_replay.asset(path)
                if asset is not None:
                    file,media=asset
                    try:data=file.read_bytes()
                    except OSError:pass
                    else:return self.send(200,data,media=media,embeddable=path==REPLAY_PAGE)
                return self.send(404,{'error':'NOT_FOUND'})
            if path=='/api/v1/session':return self.send(200,{'role':role})
            if path=='/api/v1/status':return self.send(200,app.status())
            if path=='/api/v1/building':return self.send(200,app.building)
            parts=path.split('/')
            endpoints={'resident','responder'}|({'snapshot'} if snapshots else set())
            # Optional /{zone}: a resident-chosen room for personal guidance (rooms only).
            zones=getattr(app,'zone_ids',None)
            zone=parts[6] if len(parts)==7 and zones is not None and parts[5] in {'resident','responder'} else None
            if (len(parts) not in {6,7} or len(parts)==7 and zone is None
                    or parts[1:4]!=['api','v1','incidents'] or parts[5] not in endpoints):
                return self.send(404,{'error':'NOT_FOUND'})
            if parts[5] in {'responder','snapshot'} and role!='responder':return self.send(403,{'error':'ROLE_DENIED'})
            if zone is not None and zone not in zones:return self.send(404,{'error':'ZONE_NOT_FOUND'})
            try:
                if parts[5]=='snapshot':result=app.snapshot(parts[4],role)
                elif zone is not None:result=app.view(parts[4],role,diagnostics=parts[5]=='responder',zone=zone)
                else:result=app.view(parts[4],role,diagnostics=parts[5]=='responder')
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
            compare=self.path==COMPARE_PATH and model_replay is not None
            if self.path!='/api/v1/scenario' and not compare:return self.send(404,{'error':'NOT_FOUND'})
            role=auth.role(self.token())
            if not role:return self.send(401,{'error':'AUTH_REQUIRED'})
            if role!='responder':return self.send(403,{'error':'ROLE_DENIED'})
            if compare:
                try:result=model_replay.compare(body)
                except ValueError as error:return self.send(400,{'error':str(error)})
                except (ImportError,OSError):return self.send(503,{'error':'비교 모델을 불러올 수 없습니다.'})
                return self.send(200,result)
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
    if tls_context is not None:
        try:server.socket=tls_context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
        except Exception:
            server.server_close()
            raise
    server.daemon_threads=True
    return server
