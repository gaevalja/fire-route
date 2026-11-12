"""Synthetic scenario occupants; never actual person detection or positioning."""
from dataclasses import asdict,dataclass

from simulator.commands import utc_time
from simulator.events import ContractError


@dataclass(frozen=True)
class OccupancyObservation:
    schema_version: int
    event_id: str
    incident_id: str
    zone_id: str
    remaining_count: int | None
    sequence: int
    timestamp_utc: str
    source: str
    data_origin: str

    @classmethod
    def parse(cls,data,nodes):
        if not isinstance(data,dict) or set(data)!=set(cls.__dataclass_fields__):raise ContractError('Invalid occupancy fields')
        if type(data['schema_version']) is not int or data['schema_version']!=1:raise ContractError('Invalid occupancy schema')
        for k in ['event_id','incident_id','zone_id','timestamp_utc','source','data_origin']:
            v=data[k]
            if not isinstance(v,str) or not v.strip() or len(v)>256 or any(c in v for c in '\r\n'):raise ContractError('Invalid occupancy identity')
        if data['zone_id'] not in nodes or data['data_origin']!='SYNTHETIC':raise ContractError('Occupancy must be synthetic in a known zone')
        if type(data['sequence']) is not int or data['sequence']<0:raise ContractError('Invalid occupancy sequence')
        if data['remaining_count'] is not None and (type(data['remaining_count']) is not int or data['remaining_count']<0):raise ContractError('Unknown count is null, otherwise nonnegative integer')
        utc_time(data['timestamp_utc'])
        return cls(**data)

    def to_dict(self):return asdict(self)
