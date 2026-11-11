"""Versioned FireRoute commands/ACKs inside CINs, not oneM2M primitives."""
from dataclasses import asdict, dataclass, fields
from datetime import datetime
import re

from simulator.events import ContractError


def utc_time(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', value):
        raise ContractError('Expected UTC RFC3339 timestamp')
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ContractError('Invalid UTC timestamp') from exc


def validate(cls, data):
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(cls)}:
        raise ContractError('Unexpected command/ACK schema fields')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ContractError('Unsupported command/ACK schema')
    if type(data['route_version']) is not int or data['route_version'] < 1:
        raise ContractError('Route version must be positive integer')
    for key, value in data.items():
        if key not in {'schema_version', 'route_version', 'route_exit'}:
            if not isinstance(value, str) or not value.strip() or len(value) > 256 or any(c in value for c in '\r\n'):
                raise ContractError('Invalid command/ACK string field')
    if data['data_origin'] != 'SYNTHETIC':
        raise ContractError('Initial display profile is synthetic only')
    utc_time(data['timestamp_utc'])


@dataclass(frozen=True)
class DisplayCommand:
    schema_version: int
    command_id: str
    incident_id: str
    event_id: str
    route_version: int
    action: str
    route_exit: str | None
    guidance_status: str
    expires_at_utc: str
    timestamp_utc: str
    source: str
    data_origin: str

    @classmethod
    def parse(cls, data, exits):
        validate(cls, data)
        action, status, target = data['action'], data['guidance_status'], data['route_exit']
        if action == 'DISPLAY_ROUTE':
            if not isinstance(target, str) or target not in exits or status != 'ROUTE_AVAILABLE':
                raise ContractError('Route command requires a known exit/status')
        elif action == 'CLEAR_ROUTE':
            if target is not None or status != 'NO_VERIFIED_ROUTE':
                raise ContractError('No-route command must clear directions')
        elif action == 'DISPLAY_STATUS':
            if target is not None or status not in {'UNKNOWN', 'STALE'}:
                raise ContractError('Unknown/stale command cannot display an exit')
        else:
            raise ContractError('Unsupported display action')
        if utc_time(data['expires_at_utc']) <= utc_time(data['timestamp_utc']):
            raise ContractError('Command expiry must follow issue time')
        return cls(**data)

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class DisplayAck:
    schema_version: int
    ack_id: str
    command_id: str
    device_id: str
    incident_id: str
    event_id: str
    route_version: int
    status: str
    reason: str
    timestamp_utc: str
    source: str
    data_origin: str

    @classmethod
    def parse(cls, data):
        validate(cls, data)
        if data['status'] not in {'APPLIED', 'REJECTED'}:
            raise ContractError('Unknown ACK status')
        if (data['status'] == 'APPLIED') != (data['reason'] == 'APPLIED'):
            raise ContractError('ACK status/reason disagree')
        return cls(**data)

    def to_dict(self):
        return asdict(self)
