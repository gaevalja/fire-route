"""Current-state contract for the unchanged fire_evac engine; no fake CSE."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from uuid import uuid4

from onem2m.client import strict_json
from simulator.commands import utc_time
from simulator.events import ContractError, utc_now

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'fire_evac_10f_v1'


def zone_metadata():
    result = {}
    for floor in range(1, 11):
        for room in range(1, 5 if floor == 1 else 10):
            result[f'F{floor}-R{room}'] = {'kind':'room','floor':floor}
        if floor == 1:
            result['F1-L'] = {'kind':'lobby','floor':1}
        else:
            for segment in range(1, 6):
                result[f'F{floor}-C{segment}'] = {'kind':'corridor','floor':floor}
        for suffix, kind in [('SA','stair'),('SB','stair'),('E','elevator')]:
            result[f'F{floor}-{suffix}'] = {'kind':kind,'floor':floor}
    result['F11-ROOF'] = {'kind':'roof','floor':11}
    return result


ZONES = zone_metadata()
RAW_FIELDS = {'schema_version','profile_id','source_manifest_sha256','seed','wind_mps','simulation_second','ended','zones'}
ENVELOPE = {'event_id','incident_id','sequence','timestamp_utc','source','data_origin'}


def source_manifest():
    directory = ROOT/'simulator/scenarios/fire_evac'
    if not directory.is_dir():
        directory = Path(sys.prefix)/'share/fire-route/scenarios/fire_evac'
    manifest = strict_json((directory/'manifest.json').read_bytes())
    names = {'README.md','config.js','engine.js','app.js','index.html','styles.css','test_engine.js'}
    if set(manifest['files_sha256']) != names or manifest['profile_id'] != PROFILE:
        raise ContractError('Unexpected selected source manifest')
    for name, digest in manifest['files_sha256'].items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != digest:
            raise ContractError('Selected source file differs from manifest')
    body = json.dumps(manifest['files_sha256'],sort_keys=True,separators=(',',':')).encode()
    if hashlib.sha256(body).hexdigest() != manifest['bundle_sha256']:
        raise ContractError('Selected source bundle digest differs')
    return manifest


def validate_raw(data, expected_hash):
    if not isinstance(data,dict) or set(data) != RAW_FIELDS:
        raise ContractError('Unexpected current scenario state fields')
    if type(data['schema_version']) is not int or data['schema_version'] != 1 or data['profile_id'] != PROFILE:
        raise ContractError('Unsupported scenario profile/schema')
    if data['source_manifest_sha256'] != expected_hash:
        raise ContractError('Scenario source revision differs')
    if type(data['seed']) is not int or not 1 <= data['seed'] <= 4294967295:
        raise ContractError('Invalid normalized seed')
    if type(data['wind_mps']) is not int or data['wind_mps'] not in {1,5,10,15}:
        raise ContractError('Invalid wind')
    if type(data['simulation_second']) is not int or not 0 <= data['simulation_second'] <= 12000:
        raise ContractError('Invalid simulated second')
    if type(data['ended']) is not bool or not isinstance(data['zones'],list) or len(data['zones']) != 162:
        raise ContractError('Invalid complete scenario state')
    seen = {}
    for zone in data['zones']:
        if not isinstance(zone,dict) or set(zone) != {'zone_id','fire_index','smoke_index','collapsed'}:
            raise ContractError('Unexpected scenario zone fields')
        node = zone['zone_id']
        if not isinstance(node,str) or node not in ZONES or node in seen or type(zone['collapsed']) is not bool:
            raise ContractError('Invalid/duplicate scenario zone')
        for key in ['fire_index','smoke_index']:
            value = zone[key]
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not 0 <= value <= 100:
                raise ContractError('Invalid scenario index')
        if zone['collapsed'] and ZONES[node]['kind'] in {'stair','elevator'}:
            raise ContractError('Source excludes stair/elevator collapse')
        seen[node] = zone
    if set(seen) != set(ZONES) or sum(z['collapsed'] for z in seen.values()) > 2:
        raise ContractError('Incomplete zones or collapse cap exceeded')
    for node,zone in seen.items():
        if ZONES[node]['kind'] == 'corridor':
            floor = ZONES[node]['floor']
            peers = [seen[f'F{floor}-C{i}'] for i in range(1,6)]
            if any(p['smoke_index'] != peers[0]['smoke_index'] for p in peers):
                raise ContractError('Corridor smoke must be shared')
            fire = sum(p['fire_index'] for p in peers)/5
        else:
            fire = zone['fire_index']
        if zone['smoke_index'] > fire+30+1e-8:
            raise ContractError('Scenario smoke cap differs')
    if data['ended'] != all(z['fire_index'] == 100 for z in seen.values()):
        raise ContractError('Scenario termination differs')
    return json.loads(json.dumps(data,allow_nan=False))


@dataclass(frozen=True)
class ScenarioFrame:
    data: dict

    @property
    def event_id(self):
        return self.data['event_id']

    def to_dict(self):
        return json.loads(json.dumps(self.data,allow_nan=False))

    @classmethod
    def parse(cls,data,expected_hash=None):
        if not isinstance(data,dict) or set(data) != RAW_FIELDS | ENVELOPE:
            raise ContractError('Unexpected ScenarioFrame fields')
        digest = expected_hash or source_manifest()['bundle_sha256']
        result = validate_raw({k:data[k] for k in RAW_FIELDS},digest)
        for key in ['event_id','incident_id','source']:
            if not isinstance(data[key],str) or not re.fullmatch(r'[A-Za-z0-9:_-]{1,128}',data[key]):
                raise ContractError('Invalid scenario identity')
        if data['data_origin'] != 'SYNTHETIC' or type(data['sequence']) is not int or data['sequence'] != data['simulation_second']+1:
            raise ContractError('Invalid scenario provenance/sequence')
        utc_time(data['timestamp_utc'])
        result.update({k:data[k] for k in ENVELOPE})
        return cls(result)


def emission(raw,incident_id,source,expected_hash):
    return ScenarioFrame.parse({**raw,'event_id':'frame-'+uuid4().hex,'incident_id':incident_id,
        'sequence':raw['simulation_second']+1,'timestamp_utc':utc_now(),'source':source,'data_origin':'SYNTHETIC'},expected_hash)


def trace_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(65536),b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_trace(path,expected_hash):
    """Bound line size; verify every source second without publishing future state."""
    with Path(path).open('rb') as stream:
        last = -1
        identity = None
        while True:
            line = stream.readline(65537)
            if not line:
                break
            if len(line) > 65536 or not line.endswith(b'\n'):
                raise ContractError('Oversized/incomplete source trace line')
            raw = validate_raw(strict_json(line),expected_hash)
            current = (raw['seed'],raw['wind_mps'])
            if raw['simulation_second'] != last+1 or identity is not None and current != identity:
                raise ContractError('Source trace ordering/identity differs')
            identity,last = current,raw['simulation_second']
            yield raw
            if raw['ended']:
                if stream.read(1):
                    raise ContractError('Source trace continues after termination')
                break
