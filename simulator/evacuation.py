"""Seeded synthetic residents and non-mutating fixed-origin guidance."""
from collections import Counter
from dataclasses import asdict,dataclass
import random

from mec.risk.evacuation import Navigation
from simulator.scenario_frames import ZONES,ScenarioFrame


@dataclass
class Resident:
    resident_id: str
    origin: str
    node: str
    walk_speed_mps: float
    departure_delay_s: float
    status: str = 'WAITING'
    target: str | None = None
    progress_m: float = 0.0
    distance_m: float = 0.0
    waiting_since: int = 0
    evacuated_at_s: int | None = None


class Evacuation:
    def __init__(self,assumptions=None):
        self.navigation = Navigation(assumptions)
        self.people = []
        self.last = None
        self.identities = set()

    def occupied(self):
        return Counter(tuple(sorted((p.node,p.target))) for p in self.people if p.target is not None)

    def accept(self,frame):
        if not isinstance(frame,ScenarioFrame):
            raise ValueError('A validated ScenarioFrame is required')
        data = frame.to_dict()
        second = data['simulation_second']
        if self.last is not None:
            if data == self.last:
                return False
            if self.last['ended']:
                raise ValueError('The original fire scenario has ended')
            if any(data[k] != self.last[k] for k in ['incident_id','source','seed','wind_mps','source_manifest_sha256']):
                raise ValueError('Scenario context changed without explicit reset')
            if second != self.last['simulation_second']+1 or data['event_id'] in self.identities:
                raise ValueError('Duplicate/conflicting/outdated/skipped simulation frame')
        elif second != 0:
            raise ValueError('An explicit scenario starts at second zero')
        else:
            self.populate(data['seed'])
        self.navigation.update(frame)
        blocked = self.navigation.blocked
        # Arrivals happen before admissions. Traversing a link never teleports.
        for person in self.people:
            if person.target is None:
                continue
            if person.node in blocked or person.target in blocked:
                person.status = 'BLOCKED_IN_TRANSIT'
                continue
            edge = self.navigation.adjacency[person.node][person.target]
            amount = min(edge.length_m-person.progress_m,self.navigation.speed(edge,person.walk_speed_mps))
            person.progress_m += amount
            person.distance_m += amount
            if person.progress_m >= edge.length_m-1e-9:
                person.node,person.target = person.target,None
                person.progress_m = 0
                person.waiting_since = second
                if person.node in self.navigation.exits:
                    person.status = 'EVACUATED'
                    person.evacuated_at_s = second
                else:
                    person.status = 'WAITING'
        occupied = self.occupied()
        for person in self.people:
            if person.target is None and person.status not in {'EVACUATED','QUEUED'}:
                # Pre-departure time is not time spent in the admission queue.
                person.waiting_since = second
        for person in sorted(self.people,key=lambda p:(p.waiting_since,p.resident_id)):
            if person.status == 'EVACUATED' or person.target is not None:
                continue
            if second < person.departure_delay_s:
                person.status = 'WAITING'
                continue
            route = self.navigation.route(person.node,person.walk_speed_mps,occupied)
            if route['status'] != 'ROUTE_AVAILABLE':
                person.status = 'NO_ROUTE'
                continue
            target = route['path'][1]
            edge = self.navigation.adjacency[person.node][target]
            if occupied[edge.key] >= edge.capacity:
                person.status = 'QUEUED'
                continue
            person.target,person.progress_m,person.status = target,0.0,'MOVING'
            occupied[edge.key] += 1
        self.last = data
        self.identities.add(data['event_id'])
        self.verify_conservation()
        return True

    def populate(self,seed):
        rng = random.Random(seed ^ 0x46524F55)
        config = self.navigation.assumptions
        self.people = []
        for room in sorted(n for n,m in ZONES.items() if m['kind'] == 'room'):
            for index in range(config['people_per_room']):
                speed = rng.uniform(config['walk_speed_min_mps'],config['walk_speed_max_mps'])
                if rng.random() < config['slow_fraction']:
                    speed *= config['slow_multiplier']
                delay = rng.uniform(config['departure_delay_min_s'],config['departure_delay_max_s'])
                self.people.append(Resident(f'{room}-p{index+1}',room,room,speed,delay))

    def fixed(self,origin=None):
        return self.navigation.route(origin or self.navigation.origin,occupied=self.occupied())

    def verify_conservation(self):
        ids = {p.resident_id for p in self.people}
        if len(ids) != len(self.people):
            raise ValueError('Duplicate resident identity')
        if any(p.status == 'EVACUATED' and (p.node not in self.navigation.exits or p.target is not None) for p in self.people):
            raise ValueError('Invalid exit completion')
        for key,count in self.occupied().items():
            if count > self.navigation.links[key].capacity:
                raise ValueError('Link capacity exceeded')

    def snapshot(self,origin=None):
        if self.last is None:
            raise ValueError('No accepted scenario frame')
        counts = Counter(p.status for p in self.people)
        evacuated = counts['EVACUATED']
        by_zone = Counter(p.node for p in self.people if p.status != 'EVACUATED')
        moving = Counter(p.node for p in self.people if p.target is not None)
        return {'schema_version':1,'event_id':self.last['event_id'],'incident_id':self.last['incident_id'],
            'simulation_second':self.last['simulation_second'],'route_version':self.last['sequence'],
            'timestamp_utc':self.last['timestamp_utc'],'data_origin':'SYNTHETIC',
            'model_id':self.navigation.assumptions['model_id'],'model_provenance':'ASSUMED_NOT_CALIBRATED',
            'policy_sha256':self.navigation.policy_hash,'fixed_route':self.fixed(origin),
            'population':{'total':len(self.people),'evacuated':evacuated,'remaining':len(self.people)-evacuated,
                          'states':dict(sorted(counts.items()))},
            'zones':[{'zone_id':node,'remaining_count':count,'moving_count':moving[node],
                      'assignment':'LAST_REACHED_NODE'} for node,count in sorted(by_zone.items())],
            'residents':[asdict(p) for p in self.people]}
