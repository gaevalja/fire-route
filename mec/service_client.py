"""Bounded real local platform/provider HTTP; fixture transports are unit-only."""
import hashlib
import json
import time
from urllib import error, request
from uuid import UUID

from mec.local_integration import local_url
from onem2m.client import RejectRedirect, strict_json

LIMIT = 1024 * 1024


class ServiceError(RuntimeError):
    def __init__(self, status=None):
        super().__init__('LOCAL_SERVICE_OPERATION_FAILED')
        self.status = status


class LocalHTTP:
    def __init__(self, root, *, aliases=(), evidence=None, access_key=None):
        self.root = local_url(root, 'local service', aliases=aliases)
        self.evidence, self.access_key = evidence, access_key
        self.opener = request.build_opener(request.ProxyHandler({}), RejectRedirect())

    def call(self, method, path, body=None, *, expected=(200,)):
        if not path.startswith('/') or any(s in path for s in ('..','?','#','://','\\')):
            raise ValueError('Invalid fixed operation path')
        data = None if body is None else json.dumps(body,allow_nan=False,separators=(',',':')).encode()
        if data is not None and len(data)>LIMIT:raise ValueError('Service request too large')
        headers={'Accept':'application/json'}
        if data is not None:headers['Content-Type']='application/json'
        if self.access_key:headers['X-FireRoute-Key']=self.access_key
        try:
            try:
                response=self.opener.open(request.Request(self.root+path,data=data,headers=headers,method=method),timeout=8)
            except error.HTTPError as exc:response=exc
            with response:
                raw=response.read(LIMIT+1);status=response.code
                media=response.headers.get_content_type()
            if len(raw)>LIMIT:raise ServiceError(status)
            if self.evidence:
                self.evidence.append('service-http.jsonl',{'method':method,'path':path,'status':status,
                    'response_sha256':hashlib.sha256(raw).hexdigest(),'body':strict_json(raw) if media=='application/json' and raw else None})
            if status not in expected:raise ServiceError(status)
            if status==204 and not raw:return None
            if media!='application/json':raise ServiceError(status)
            return strict_json(raw)
        except (error.URLError,OSError,TimeoutError,ValueError):
            raise ServiceError() from None


def actual_id(value):
    if not isinstance(value,str):raise ServiceError()
    try:UUID(value)
    except ValueError:raise ServiceError() from None
    return value


RISK_ENDPOINT='http://mec-risk:8081/v1/frames'
OCCUPANCY_ENDPOINT='http://mec-occupancy:8082/v1/batches'
OCCUPANCY_SERVICE='FireRoute Occupancy v1'


def register_risk(controller, platform, name, *, saved=None, save=lambda value:None):
    return register_service(controller,platform,name,RISK_ENDPOINT,saved=saved,save=save)


def register_service(controller, platform, name, endpoint, *, saved=None, save=lambda value:None):
    """Use server-allocated IDs; no Redis access and no uncertain POST replay."""
    if saved is None:
        saved={'name':name,'app_create_attempted':True};save(saved)
        app=controller.call('POST','/sandbox-ctrl/v1/applications',
                            {'name':name,'nodeName':'mep1','type':'USER','persist':True},expected=(201,))
        appid=actual_id(app.get('id'))
        saved={**saved,'app_id':appid};save(saved)
    elif not saved.get('app_id'):
        # A previously submitted POST is never replayed. Recover only an
        # unambiguous real platform assignment belonging to this saved name.
        apps=controller.call('GET','/sandbox-ctrl/v1/applications')
        if apps is not None and (not isinstance(apps,list) or any(not isinstance(a,dict) for a in apps)):
            raise ServiceError()
        matches=[a for a in apps or [] if a.get('name')==name and a.get('nodeName')=='mep1']
        if saved.get('name')!=name or len(matches)!=1:raise ServiceError()
        saved={**saved,'app_id':actual_id(matches[0].get('id'))};save(saved)
    appid=actual_id(saved['app_id'])
    app=controller.call('GET','/sandbox-ctrl/v1/applications/'+appid)
    if app.get('id')!=appid or app.get('name')!=name or app.get('nodeName')!='mep1':raise ServiceError()
    # GET waits only for the controller's asynchronous app-store update.
    deadline=time.monotonic()+30
    while True:
        try:
            platform.call('POST','/mec_app_support/v2/applications/'+appid+'/confirm_ready',
                          {'indication':'READY'},expected=(204,));break
        except ServiceError as exc:
            if exc.status!=404 or time.monotonic()>=deadline:raise
            time.sleep(.2)
    path='/mec_service_mgmt/v1/applications/'+appid+'/services'
    services=platform.call('GET',path)
    if not isinstance(services,list) or any(not isinstance(s,dict) for s in services):raise ServiceError()
    matches=[s for s in services if s.get('serName')==name]
    if not matches:
        if saved.get('service_create_attempted'):raise ServiceError()
        saved={**saved,'service_create_attempted':True};save(saved)
        info=platform.call('POST',path,{'serName':name,'version':'1.0','state':'ACTIVE','serializer':'JSON',
            'scopeOfLocality':'MEC_SYSTEM','consumedLocalOnly':False,
            'transportInfo':{'id':'fire-route-http','name':'FireRoute authenticated JSON',
                'type':'REST_HTTP','protocol':'HTTP','version':'1.1',
                'endpoint':{'uris':[endpoint]},'security':{}}},expected=(201,))
    elif len(matches)==1:info=matches[0]
    else:raise ServiceError()
    sid=actual_id(info.get('serInstanceId'))
    if info.get('transportInfo',{}).get('endpoint',{}).get('uris')!=[endpoint]:
        raise ServiceError()
    readback=platform.call('GET',path+'/'+sid)
    if readback!=info:raise ServiceError()
    result={**saved,'service_id':sid,'service':info}
    save(result)
    return result


def discover_risk(platform, name, service_id):
    return discover_service(platform,name,service_id,RISK_ENDPOINT)


def discover_service(platform, name, service_id, endpoint):
    catalog=platform.call('GET','/mec_service_mgmt/v1/services')
    if not isinstance(catalog,list) or any(not isinstance(s,dict) for s in catalog):raise ServiceError()
    found=[s for s in catalog if s.get('serName')==name and s.get('serInstanceId')==service_id]
    if len(found)!=1:raise ServiceError()
    item=found[0]
    if (item.get('state')!='ACTIVE' or item.get('serializer')!='JSON'
            or item.get('transportInfo',{}).get('endpoint',{}).get('uris')!=[endpoint]):
        raise ServiceError()
    return item
