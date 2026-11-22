"""MEC 011 service discovery adapter, not a simulated MEC platform or MEC-IPE.

Paths and required ServiceInfo fields follow ETSI's published Service Management
OpenAPI (inspected reference v2.0.9). Runtime API/version support is not assumed.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import ssl
from urllib import request,error
from urllib.parse import quote,urlsplit
from uuid import uuid4

from backend.config import http_url
from backend.evidence import redact
from onem2m.client import RejectRedirect,strict_json
from simulator.events import utc_now


class MECError(RuntimeError):
    def __init__(self,message,*,http_status=None):
        super().__init__(message);self.http_status=http_status
class MECUnavailable(MECError):pass


@dataclass(frozen=True)
class CatalogSettings:
    service_management_url: str
    environment: str
    application_instance_id: str = ''
    token_file: Path | None = None
    ca_file: Path | None = None

    def __post_init__(self):
        url=http_url(self.service_management_url,'MEC_SERVICE_MGMT_URL')
        p=urlsplit(url)
        if self.environment not in {'local-sandbox','hosted-sandbox'}:
            raise ValueError('Explicit MEC environment required')
        if not p.path.endswith('/mec_service_mgmt/v1'):
            raise ValueError('Configured MEC URL must identify the v1 Service Management API root')
        if p.scheme!='https' and (self.environment!='local-sandbox' or self.token_file):
            raise ValueError('Hosted MEC and bearer credentials require HTTPS')
        if self.environment=='hosted-sandbox' and p.hostname in {'localhost','127.0.0.1','::1'}:
            raise ValueError('Hosted MEC cannot use the local loopback address')
        if (not isinstance(self.application_instance_id,str) or len(self.application_instance_id)>128
            or self.application_instance_id in {'.','..'}
            or any(ord(c)<33 or c in '/?#\\' for c in self.application_instance_id)):
            raise ValueError('Invalid MEC application instance ID')


class DiscoveryTransport:
    def __init__(self,settings):
        self.settings=settings
        try:context=ssl.create_default_context(cafile=str(settings.ca_file) if settings.ca_file else None)
        except (OSError,ssl.SSLError):raise ValueError('MEC CA unavailable or invalid') from None
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        self.opener=request.build_opener(RejectRedirect(),request.HTTPSHandler(context=context))
        self.token=None
        if settings.token_file:
            p=Path(settings.token_file)
            if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o077:
                raise ValueError('MEC token file must be private and regular')
            self.token=p.read_text().strip()
            if not self.token or len(self.token)>8192 or any(c.isspace() for c in self.token):
                raise ValueError('Invalid MEC bearer token')

    def __call__(self,url):
        headers={'Accept':'application/json'}
        if self.token:headers['Authorization']='Bearer '+self.token
        req=request.Request(url,headers=headers,method='GET')
        try:
            with self.opener.open(req,timeout=10) as response:
                body=response.read(1024*1024+1)
                return response.status,dict(response.headers),body
        except error.HTTPError as exc:
            # Do not export redirects, login pages, tokens or error response bodies.
            raise MECError('MEC discovery rejected',http_status=exc.code) from None
        except (error.URLError,OSError,TimeoutError):
            raise MECUnavailable('MEC service discovery transport unavailable') from None


def discover(settings,*,transport=None):
    base=settings.service_management_url.rstrip('/')
    suffix='/applications/'+quote(settings.application_instance_id,safe='')+'/services' if settings.application_instance_id else '/services'
    caller=transport or DiscoveryTransport(settings)
    status,headers,body=caller(base+suffix)
    if status!=200:raise MECError('MEC service discovery requires an actual HTTP 200',http_status=status)
    media=next((v for k,v in headers.items() if k.lower()=='content-type'),'').split(';')[0].lower()
    if media!='application/json' or len(body)>1024*1024:raise MECError('Invalid MEC discovery representation')
    try:
        raw=strict_json(body)
        if not isinstance(raw,list) or len(raw)>1000:raise ValueError()
        safe=[];ids=set()
        for item in raw:
            if not isinstance(item,dict):raise ValueError()
            for key in ('serName','version','state','serializer'):
                if not isinstance(item.get(key),str) or not item[key] or len(item[key])>256:raise ValueError()
            if item['state'] not in {'ACTIVE','INACTIVE'} or not isinstance(item.get('transportInfo'),dict):raise ValueError()
            identity=item.get('serInstanceId')
            if identity is not None:
                if not isinstance(identity,str) or not identity or identity in ids:raise ValueError()
                ids.add(identity)
            # Persist only approved discovery metadata. Never copy an endpoint,
            # OAuth security block, arbitrary response field or credential to CSE.
            record={k:item[k] for k in ('serName','version','state','serializer')}
            if identity is not None:record['serInstanceId']=identity
            for key in ('type','protocol','version'):
                value=item['transportInfo'].get(key)
                if isinstance(value,str) and len(value)<=128:record['transport_'+key]=value
            safe.append(record)
    except (ValueError,TypeError,KeyError,UnicodeDecodeError):
        raise MECError('Malformed MEC ServiceInfo list') from None
    return redact({'schema_version':1,'event_id':'mec-'+uuid4().hex,'observed_at_utc':utc_now(),'http_status':status,
            'MEC_API':'MEC011_SERVICE_DISCOVERY','contract_reference':'ETSI_MEC011_OpenAPI_v2.0.9_compatible_subset',
            'MEC_environment':settings.environment,'consumption_path':'DIRECT_MEC_API',
            'MEC_IPE':'NOT_IMPLEMENTED','deployment':'NOT_VERIFIED_BY_DISCOVERY',
            'service_count':len(safe),'services':safe,'response_sha256':hashlib.sha256(body).hexdigest()},
            tuple([caller.token]) if getattr(caller,'token',None) else ())


def persist_catalog(client,container,snapshot):
    """Application AE bridge into an existing real CNT, not a standard MEC-IPE.

    Operator supplies a scoped existing container and credential; no bootstrap
    admin or fabricated AE is inferred. The real CSE enforces its ACP.
    """
    if snapshot.get('MEC_API')!='MEC011_SERVICE_DISCOVERY' or snapshot.get('consumption_path')!='DIRECT_MEC_API':
        raise ValueError('Actual discovery snapshot required')
    target=client.resource(client.retrieve(container),3)
    if not isinstance(target.get('lbl'),list) or 'fire-route:mec-catalog' not in target['lbl']:
        raise ValueError('Refusing to write outside the dedicated MEC catalog container')
    name='catalog-'+uuid4().hex
    result=client.resource(client.create(container,4,{'rn':name,'cnf':'application/json:0',
        'con':json.dumps({**snapshot,'consumption_path':'APPLICATION_AE_BRIDGE_NOT_MEC_IPE'},separators=(',',':'))}),4)
    actual=client.resource(client.retrieve(container+'/'+name),4)
    expected={**snapshot,'consumption_path':'APPLICATION_AE_BRIDGE_NOT_MEC_IPE'}
    if actual['ri']!=result['ri'] or strict_json(actual['con'])!=expected:
        raise MECError('Actual CSE catalog read-back mismatch')
    return {'path':container+'/'+name,'cin_ri':actual['ri'],'MEC_IPE':'NOT_IMPLEMENTED'}
