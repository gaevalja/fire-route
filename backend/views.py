"""Role-filtered views read actual CSE resources; never fabricate live state."""
from datetime import datetime,timezone

from onem2m.client import ProtocolError,strict_json
from simulator.commands import utc_time
from simulator.occupancy import OccupancyObservation


def latest(client,resources,key):
    path=resources['containers'][key]['path']+'/la'
    cin=client.resource(client.retrieve(path),4)
    value=strict_json(cin['con']) if isinstance(cin['con'],str) else cin['con']
    if not isinstance(value,dict) or type(value.get('schema_version')) is not int or value['schema_version']!=1:
        raise ProtocolError('Invalid application CIN envelope')
    return value


def unknown_view(incident_id,*,status='UNKNOWN',cse='UNAVAILABLE'):
    return {'schema_version':1,'incident_id':incident_id,'route_version':None,
        'guidance_status':status,'route':None,'delivery':{'state':'UNKNOWN','ack_count':None,'expected_ack_count':3},
        'observed_at_utc':None,'verified_at_utc':datetime.now(timezone.utc).isoformat(),
        'data_origin':'SYNTHETIC','connections':{'cse':cse,'mec':'UNAVAILABLE'},
        'deployment_option':'standalone_dev_IN_CSE_NOT_MEC'}


class LiveViews:
    def __init__(self,clients,resources,graph,incident_id,settings):
        self.clients,self.resources,self.graph,self.incident_id,self.settings=clients,resources,graph,incident_id,settings

    def read(self,role,*,diagnostics=False,now=None):
        if role not in {'resident','responder'} or diagnostics and role!='responder':
            raise PermissionError('Responder role required')
        client=self.clients[role]
        route=latest(client,self.resources,'controller/routes')
        status=latest(client,self.resources,'controller/status')
        current=datetime.now(timezone.utc) if now is None else now
        result=unknown_view(self.incident_id,cse='LIVE')
        if route.get('incident_id')!=self.incident_id or status.get('incident_id')!=self.incident_id:
            raise ProtocolError('CSE incident correlation differs')
        if any(route.get(k)!=status.get(k) for k in ['event_id','route_version']):
            result['guidance_status']='PENDING'
            return result
        if type(route.get('route_version')) is not int or route['route_version']<1:
            raise ProtocolError('Invalid CSE route version')
        try:
            computed=self.graph.route(route['source_node'],route['blocked_nodes'])
            if (route['source_node']!=self.graph.origin or route['target_exit']!=computed.target_exit
                    or route['path']!=list(computed.path) or route['status']!=computed.status):
                raise ValueError('Route content differs from graph')
            age=(current-utc_time(status['observed_at_utc'])).total_seconds()
            delivery=status['delivery']
            count=delivery['ack_count'];expected=delivery['expected_ack_count']
            if type(count) is not int or not 0<=count<=3 or type(expected) is not int or expected!=3:
                raise ValueError('Invalid delivery count')
            if delivery['state'] not in {'ALL_ACKED','INCOMPLETE'} or (delivery['state']=='ALL_ACKED')!=(count==3):
                raise ValueError('Delivery state/count disagree')
        except (ValueError,TypeError,KeyError) as exc:
            raise ProtocolError('Malformed CSE route/status content') from exc
        result.update(route_version=route['route_version'],observed_at_utc=status['observed_at_utc'],
                      delivery={k:delivery[k] for k in ['state','ack_count','expected_ack_count']})
        if age< -self.settings.max_clock_skew:result['guidance_status']='UNKNOWN'
        elif age>=self.settings.sensor_ttl:result['guidance_status']='STALE'
        else:
            result['guidance_status']=route['status']
            if route['status']=='ROUTE_AVAILABLE':
                result['route']={k:route[k] for k in ['source_node','target_exit','path']}
        if diagnostics:
            hazard=latest(client,self.resources,'controller/hazards')
            detail=latest(client,self.resources,'controller/diagnostics')
            if any(hazard.get(k)!=route.get(k) or detail.get(k)!=route.get(k) for k in ['event_id','incident_id','route_version']):
                result.update(guidance_status='PENDING',route=None)
                return result
            if not isinstance(detail.get('devices'),list) or not isinstance(detail.get('sensors'),list):
                raise ProtocolError('Malformed CSE diagnostics')
            # Explicit fields only; no CSE paths, credentials, or arbitrary JSON passthrough.
            result['hazards']={'blocked_nodes':hazard['blocked_nodes']}
            result['devices']=[{k:d.get(k) for k in ['device','status','ack_timestamp_utc']} for d in detail['devices']]
            for device in result['devices']:
                if device['status']=='APPLIED':
                    ack_age=(current-utc_time(device['ack_timestamp_utc'])).total_seconds()
                    if ack_age>=self.settings.sensor_ttl:device['status']='STALE'
                    elif ack_age< -self.settings.max_clock_skew:device['status']='UNKNOWN'
            result['sensors']=[{k:s.get(k) for k in ['sensor_id','sensor_type','location_node','value','unit','timestamp_utc','data_origin']} for s in detail['sensors']]
            snapshot=latest(client,self.resources,'occupancy/observations')
            if snapshot.get('incident_id')!=self.incident_id or snapshot.get('data_origin')!='SYNTHETIC':
                raise ProtocolError('Invalid synthetic occupant snapshot')
            entries=snapshot.get('observations')
            if not isinstance(entries,list) or not 1<=len(entries)<=100:raise ProtocolError('Invalid occupant entries')
            occupants=[]
            for entry in entries:
                item=OccupancyObservation.parse(entry,self.graph.nodes)
                if item.incident_id!=self.incident_id:raise ProtocolError('Occupant incident differs')
                fresh=-self.settings.max_clock_skew<=(current-utc_time(item.timestamp_utc)).total_seconds()<self.settings.sensor_ttl
                occupants.append({'zone_id':item.zone_id,'remaining_count':item.remaining_count if fresh else None,
                    'status':'KNOWN' if fresh and item.remaining_count is not None else 'UNKNOWN',
                    'timestamp_utc':item.timestamp_utc,'data_origin':'SYNTHETIC'})
            result['occupants']=occupants
        return result
