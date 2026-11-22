"""Independent acceptance checks, never a CSE or a fire-model replacement."""
from collections import Counter,deque
import math

from backend.delivery import ROLES
from simulator.scenario_frames import ScenarioFrame,source_manifest

STAGES = frozenset({'baseline','alternative','collapse','isolated'})
STATES = {'WAITING','QUEUED','MOVING','EVACUATED','NO_ROUTE','BLOCKED_IN_TRANSIT'}


class HazardCoverage:
    def __init__(self,navigation):
        self.navigation=navigation
        self.digest=source_manifest()['bundle_sha256']
        self.baseline=None
        self.stages={}
        self.adj={n:set(peers) for n,peers in navigation.adjacency.items()}

    @property
    def complete(self):
        return set(self.stages)==STAGES

    def reachable(self,blocked):
        """BFS oracle checks existence independently of weighted route selection."""
        queue=deque([self.navigation.origin]);seen=set()
        while queue:
            node=queue.popleft()
            if node in seen or node in blocked:continue
            if node in self.navigation.exits:return True
            seen.add(node);queue.extend(self.adj[node]-seen)
        return False

    def observe(self,frame,result):
        data=ScenarioFrame.parse(frame,self.digest).to_dict()
        expected={'event_id':data['event_id'],'incident_id':data['incident_id'],
            'simulation_second':data['simulation_second'],'route_version':data['sequence'],
            'timestamp_utc':data['timestamp_utc'],'data_origin':'SYNTHETIC',
            'policy_sha256':self.navigation.policy_hash}
        if any(result.get(k)!=v for k,v in expected.items()):
            raise AssertionError('Hazard result correlation differs')
        policy=self.navigation.assumptions
        collapsed={z['zone_id'] for z in data['zones'] if z['collapsed']}
        blocked={z['zone_id'] for z in data['zones'] if z['collapsed']
            or z['fire_index']>=policy['fire_block_index'] or z['smoke_index']>=policy['smoke_block_index']}
        route=result['fixed_route'];path=route['path'];reachable=self.reachable(blocked)
        if route['source_node']!=self.navigation.origin or route['cost_unit']!='ASSUMED_SECONDS':
            raise AssertionError('Hazard fixed origin/cost unit differs')
        if reachable:
            cost=route['routing_cost']
            if (route['status']!='ROUTE_AVAILABLE' or not path or path[0]!=self.navigation.origin
                    or path[-1]!=route['target_exit'] or path[-1] not in self.navigation.exits
                    or len(path)!=len(set(path)) or set(path)&blocked
                    or any(b not in self.adj.get(a,set()) for a,b in zip(path,path[1:]))
                    or isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0):
                raise AssertionError('Available route crosses hazard or differs from reachability')
        elif (route['status']!='NO_VERIFIED_ROUTE' or path or route['target_exit'] is not None
                or route['routing_cost'] is not None):
            raise AssertionError('No-route result fabricates guidance')
        pop=result['population'];people=result['residents']
        if (any(type(pop[k]) is not int or pop[k]<0 for k in ['total','evacuated','remaining'])
                or pop['total']!=pop['evacuated']+pop['remaining'] or len(people)!=pop['total']
                or len({p['resident_id'] for p in people})!=len(people)
                or any(p['status'] not in STATES for p in people)
                or Counter(p['status'] for p in people)!=Counter(pop['states'])
                or pop['evacuated']!=sum(p['status']=='EVACUATED' for p in people)
                or any(p['node'] not in self.navigation.exits or p['target'] is not None
                       for p in people if p['status']=='EVACUATED')
                or sum(z['remaining_count'] for z in result['zones'])!=pop['remaining']):
            raise AssertionError('Hazard population is lost or fabricated')
        if self.baseline is None:
            if data['simulation_second']!=0 or blocked or not reachable:
                raise AssertionError('Hazard baseline must start at an unblocked second zero')
            self.baseline=list(path)
        blocked_baseline=sorted(set(self.baseline)&blocked)
        flags={'baseline':data['simulation_second']==0,
            'alternative':reachable and bool(blocked_baseline) and path!=self.baseline,
            'collapse':bool(collapsed),
            'isolated':not reachable and self.navigation.origin not in blocked}
        new=[]
        for stage,matched in flags.items():
            if matched and stage not in self.stages:
                record={'stage':stage,'simulation_second':data['simulation_second'],
                    'event_id':data['event_id'],'route_version':data['sequence'],
                    'reachable_by_BFS':reachable,'blocked_nodes':sorted(blocked),
                    'blocked_baseline_nodes':blocked_baseline,'collapsed_nodes':sorted(collapsed),
                    'fixed_route':route,'population':pop}
                self.stages[stage]=record;new.append(record)
        return new


def verify_delivery(result,delivery,*,missing=()):
    """Check recorded fan-out/ACK/device state; transport is verified by DeliverySession."""
    absent=set(missing);expected=set(ROLES)-absent;command=delivery['command']
    route=result['fixed_route']
    if not absent<=set(ROLES):raise AssertionError('Unknown expected missing device')
    if (type(delivery['ack_count']) is not int or delivery['ack_count']!=len(expected)
            or delivery['state']!=('INCOMPLETE' if absent else 'ALL_ACKED')
            or set(delivery['missing_devices'])!=absent
            or set(delivery['acks'])!=expected or set(delivery['display_states'])!=expected):
        raise AssertionError('Delivery completion differs from independent device set')
    members=delivery['fanout']['members']
    if set(members)!=set(ROLES) or len({x['ri'] for x in members.values()})!=3:
        raise AssertionError('Group did not create three distinct member CINs')
    for key in ['event_id','incident_id','route_version']:
        if command[key]!=result[key]:raise AssertionError('Command correlation differs')
    if (command['route_exit']!=route['target_exit'] or command['guidance_status']!=route['status']
            or command['action']!=('DISPLAY_ROUTE' if route['status']=='ROUTE_AVAILABLE' else 'CLEAR_ROUTE')):
        raise AssertionError('Command differs from verified hazard route')
    ids=set()
    for role in expected:
        ack=delivery['acks'][role]['ack'];state=delivery['display_states'][role]
        if (ack['device_id'] in ids or ack['status']!='APPLIED'
                or any(ack[k]!=command[k] for k in ['command_id','event_id','incident_id','route_version'])
                or any(state[k]!=command[k] for k in ['command_id','route_version','route_exit','guidance_status'])):
            raise AssertionError('Device ACK/state differs from current command')
        ids.add(ack['device_id'])
