"""Assumed schematic pedestrian network; not a calibrated evacuation predictor."""
from dataclasses import dataclass
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys

from simulator.scenario_frames import ROOT, ZONES


def load_assumptions(path=None):
    path = Path(path) if path else ROOT/'fixtures/evacuation_assumptions.json'
    if not path.is_file():
        path = Path(sys.prefix)/'share/fire-route/fixtures/evacuation_assumptions.json'
    data = json.loads(path.read_text())
    validate_assumptions(data)
    return data


def validate_assumptions(data):
    positive = {'walk_speed_min_mps','walk_speed_max_mps','slow_multiplier','stair_speed_multiplier',
        'room_door_length_m','corridor_link_length_m','stair_floor_length_m','lobby_link_length_m','exit_link_length_m'}
    nonnegative = {'departure_delay_min_s','departure_delay_max_s'}
    capacities = {'door_capacity_people','corridor_capacity_people','stair_capacity_people','exit_capacity_people'}
    fractions = {'slow_fraction','smoke_slowdown_fraction'}
    indices = {'fire_block_index','smoke_block_index'}
    required = positive|nonnegative|capacities|fractions|indices|{'schema_version','model_id','provenance','people_per_room','fixed_origin'}
    if not isinstance(data,dict) or set(data) != required or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('Unexpected evacuation assumptions schema')
    if data['model_id'] != 'fire-route-network-v1' or data['provenance'] != 'ASSUMED_NOT_CALIBRATED':
        raise ValueError('Model assumptions must retain explicit provenance')
    if not isinstance(data['fixed_origin'],str) or data['fixed_origin'] not in ZONES or ZONES[data['fixed_origin']]['kind']!='room':
        raise ValueError('Fixed origin must be a known room')
    for key in positive|nonnegative|fractions|indices:
        value = data[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
            raise ValueError('Invalid model number')
        if key in positive and value <= 0 or key in nonnegative and value < 0:
            raise ValueError('Invalid model bound')
    for key in capacities:
        if type(data[key]) is not int or not 1 <= data[key] <= 1000:
            raise ValueError('Invalid edge capacity')
    if type(data['people_per_room']) is not int or not 0 <= data['people_per_room'] <= 10:
        raise ValueError('Invalid population size')
    if any(not 0 <= data[k] <= 1 for k in fractions) or data['smoke_slowdown_fraction'] >= 1:
        raise ValueError('Invalid assumed fraction')
    if any(not 0 < data[k] <= 100 for k in indices):
        raise ValueError('Invalid demo blocking index')
    if (data['walk_speed_min_mps'] > data['walk_speed_max_mps'] or data['walk_speed_max_mps'] > 5
            or data['departure_delay_min_s'] > data['departure_delay_max_s'] or data['departure_delay_max_s'] > 3600
            or data['slow_multiplier'] > 1 or data['stair_speed_multiplier'] > 1):
        raise ValueError('Invalid model parameter ordering/range')


@dataclass(frozen=True)
class Link:
    start: str
    end: str
    length_m: float
    capacity: int
    kind: str

    @property
    def key(self):
        return tuple(sorted((self.start,self.end)))


class Navigation:
    def __init__(self,assumptions=None):
        self.assumptions = dict(load_assumptions() if assumptions is None else assumptions)
        validate_assumptions(self.assumptions)
        self.policy_hash = hashlib.sha256(json.dumps(self.assumptions,sort_keys=True).encode()).hexdigest()
        self.metadata = {**ZONES,'EXIT_A':{'kind':'exit','floor':1},'EXIT_B':{'kind':'exit','floor':1}}
        self.exits = frozenset({'EXIT_A','EXIT_B'})
        self.nodes = frozenset(self.metadata)
        self.origin = self.assumptions['fixed_origin']
        self.adjacency = {n:{} for n in self.nodes}
        self.links = {}
        self.hazards = None
        for floor in range(1,11):
            if floor == 1:
                for suffix in ['R1','R2','R3','R4','SA','SB']:
                    self.link('F1-L','F1-'+suffix,'door' if suffix.startswith('R') else 'lobby')
            else:
                for index in range(1,6):
                    corridor = f'F{floor}-C{index}'
                    self.link(corridor,f'F{floor}-R{index}','door')
                    if index < 5:
                        self.link(corridor,f'F{floor}-C{index+1}','corridor')
                for index,room in [(1,6),(2,7),(4,8),(5,9)]:
                    self.link(f'F{floor}-C{index}',f'F{floor}-R{room}','door')
                self.link(f'F{floor}-C1',f'F{floor}-SA','corridor')
                self.link(f'F{floor}-C5',f'F{floor}-SB','corridor')
            if floor < 10:
                for side in ['A','B']:
                    self.link(f'F{floor}-S{side}',f'F{floor+1}-S{side}','stair')
        for side in ['A','B']:
            self.link('F10-S'+side,'F11-ROOF','stair')
            self.link('F1-L','EXIT_'+side,'exit')

    def link(self,a,b,kind):
        length_key = {'door':'room_door_length_m','corridor':'corridor_link_length_m',
            'lobby':'lobby_link_length_m','stair':'stair_floor_length_m','exit':'exit_link_length_m'}[kind]
        capacity_key = ('corridor' if kind == 'lobby' else kind)+'_capacity_people'
        edge = Link(a,b,float(self.assumptions[length_key]),self.assumptions[capacity_key],kind)
        self.links[edge.key] = edge
        self.adjacency[a][b] = self.adjacency[b][a] = edge

    def update(self,frame):
        self.hazards = {z['zone_id']:dict(z) for z in frame.to_dict()['zones']}

    @property
    def blocked(self):
        if self.hazards is None:
            raise ValueError('No current validated hazard frame')
        p = self.assumptions
        return frozenset(n for n,z in self.hazards.items() if z['collapsed']
            or z['fire_index'] >= p['fire_block_index'] or z['smoke_index'] >= p['smoke_block_index'])

    def speed(self,edge,walk_speed):
        smoke = max(self.hazards.get(n,{}).get('smoke_index',0) for n in [edge.start,edge.end])
        scale = 1-self.assumptions['smoke_slowdown_fraction']*smoke/100
        return walk_speed*scale*(self.assumptions['stair_speed_multiplier'] if edge.kind == 'stair' else 1)

    def route(self,origin,walk_speed=1.1,occupied=None):
        if origin not in self.nodes or isinstance(walk_speed,bool) or not math.isfinite(walk_speed) or walk_speed <= 0:
            raise ValueError('Invalid evacuation route input')
        blocked = self.blocked
        occupied = occupied or {}
        queue = [(0.0,(origin,),origin)]
        visited = set()
        while queue:
            cost,path,node = heapq.heappop(queue)
            if node in visited or node in blocked:
                continue
            visited.add(node)
            if node in self.exits:
                return {'source_node':origin,'status':'ROUTE_AVAILABLE','target_exit':node,
                    'path':list(path),'routing_cost':cost,'cost_unit':'ASSUMED_SECONDS'}
            for target,edge in sorted(self.adjacency[node].items()):
                if target in blocked or target in visited:
                    continue
                travel = edge.length_m/self.speed(edge,walk_speed)
                delay = travel*occupied.get(edge.key,0)/edge.capacity
                heapq.heappush(queue,(cost+travel+delay,path+(target,),target))
        return {'source_node':origin,'status':'NO_VERIFIED_ROUTE','target_exit':None,
            'path':[],'routing_cost':None,'cost_unit':'ASSUMED_SECONDS'}

    def document(self):
        return {'model_id':self.assumptions['model_id'],'provenance':self.assumptions['provenance'],
            'policy_sha256':self.policy_hash,'origin_node':self.origin,'exits':sorted(self.exits),
            'nodes':[{'id':n,**m} for n,m in self.metadata.items()],
            'edges':[{'from':e.start,'to':e.end,'length_m':e.length_m,'capacity_people':e.capacity,
                      'kind':e.kind,'bidirectional':True} for e in self.links.values()]}
