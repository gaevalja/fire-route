"""Coordinate real fan-out, independent processes and CSE-backed ACK evidence."""
from datetime import datetime, timedelta, timezone
import multiprocessing
import os
from pathlib import Path
import queue
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from backend.p0 import subscription_refs
from onem2m.client import ProtocolError, strict_json
from onem2m.groups import create_display_group, fanout_command
from simulator.commands import DisplayAck, DisplayCommand
from simulator.displays import DisplayState, ack_name, device_worker

ROLES = ('display-a','display-b','display-c')


def display_callbacks(settings):
    parsed = urlsplit(settings.notification_url)
    if parsed.scheme != 'http' or settings.bind_port + 3 >= 65536:
        raise ValueError('Group smoke requires isolated HTTP and three adjacent private ports')
    host = parsed.hostname
    host = '[' + host + ']' if ':' in host else host
    return {role:urlunsplit(('http',f'{host}:{settings.bind_port+i}','/onem2m/notify','','')) for i,role in enumerate(ROLES,1)}


class AckSet:
    def __init__(self, command, device_ids, *, sources=None):
        self.command, self.expected, self.applied = command, set(device_ids), {}
        self.ack_ids = {}
        self.sources = sources or {}

    def add(self, data, bound_device):
        ack = DisplayAck.parse(data)
        if ack.command_id != self.command.command_id:
            return False
        if bound_device not in self.expected or ack.device_id != bound_device:
            raise ProtocolError('ACK device identity differs from its actual subscription binding')
        if bound_device in self.sources and ack.source != self.sources[bound_device]:
            raise ProtocolError('ACK logical source differs')
        for key in ['event_id','incident_id','route_version','data_origin']:
            if getattr(ack,key) != getattr(self.command,key):
                raise ProtocolError('ACK correlation differs')
        if ack.ack_id in self.ack_ids and self.ack_ids[ack.ack_id] != bound_device:
            raise ProtocolError('One ACK identity reused across devices')
        if ack.status != 'APPLIED':
            raise ProtocolError('Device rejected the expected valid command')
        if bound_device in self.applied and self.applied[bound_device] != ack.to_dict():
            raise ProtocolError('Conflicting ACKs for one device/command')
        self.ack_ids[ack.ack_id] = bound_device
        self.applied[bound_device] = ack.to_dict()
        return True

    @property
    def missing(self):
        return self.expected - self.applied.keys()


class DeliverySession:
    def __init__(self, settings, admin, controller, resources, cb, service, inbox, graph, incident_id, evidence):
        self.settings, self.controller, self.resources = settings, controller, resources
        self.service, self.inbox, self.graph, self.evidence = service, inbox, graph, evidence
        self.context = multiprocessing.get_context('spawn')
        self.messages = self.context.Queue()
        self.processes, self.stops, self.configs, self.ack_refs, self.ready = {}, {}, {}, {}, {}
        self.results = []
        self.group = create_display_group(admin, controller, resources, settings.retention_seconds)
        self.callbacks = display_callbacks(settings)
        self.cb, self.incident_id = cb, incident_id

    def start(self):
        for i,role in enumerate(ROLES,1):
            directory = (self.evidence.path / 'devices' / role).resolve()
            config = {'directory':str(directory), 'state_path':str(directory/'display.sqlite3'),
                'role':role, 'ae_id':self.resources['actors'][role]['ae_id'],
                'cse_url':self.settings.cse_url, 'release':self.settings.release, 'cse_id':self.cb['csi'],
                'commands':self.resources['containers'][role+'/commands']['path'],
                'acks':self.resources['containers'][role+'/acks']['path'], 'incident_id':self.incident_id,
                'controller_source':self.resources['namespace']+':controller', 'source':self.resources['namespace']+':'+role,
                'exits':list(self.graph.exits), 'bind_host':self.settings.bind_host, 'port':self.settings.bind_port+i,
                'callback':self.callbacks[role], 'request_timeout':self.settings.request_timeout,
                'max_skew':self.settings.max_clock_skew, 'retry_limit':self.settings.retry_limit}
            self.configs[role] = config
            stop = self.context.Event()
            process = self.context.Process(target=device_worker,args=(config,stop,self.messages),name=role)
            self.stops[role], self.processes[role] = stop, process
            process.start()
        deadline = time.monotonic() + self.settings.startup_timeout
        while len(self.ready) < 3:
            try:
                message = self.messages.get(timeout=max(0.01,deadline-time.monotonic()))
            except queue.Empty as exc:
                raise ProtocolError('Independent display startup deadline exceeded') from exc
            role = message['role']
            if (message['kind'] != 'ready' or role not in self.processes or role in self.ready
                    or message['pid'] != self.processes[role].pid or message['ae_id'] != self.configs[role]['ae_id']):
                raise ProtocolError('Independent display startup failed or returned wrong identity')
            self.ready[role] = message
        if len({x['pid'] for x in self.ready.values()} | {os.getpid()}) != 4:
            raise ProtocolError('Display consumers are not three independent processes')
        self.evidence.write('devices.json', self.ready)
        self.evidence.write('group.json', self.group)
        for role in ROLES:
            parent = self.resources['containers'][role+'/acks']['path']
            sub = self.controller.ensure(parent,23,{'rn':'controller-sub','nu':[self.settings.notification_url],'enc':{'net':[3]},'nct':1})
            refs = subscription_refs(self.cb['csi'],parent+'/controller-sub',sub)
            if not refs & self.inbox.verified_refs():
                raise ProtocolError('Controller ACK SUB verification missing')
            self.service.approve(refs,decoder=DisplayAck.parse,identity_field='ack_id')
            for ref in refs:
                self.ack_refs[ref] = role

    def check_workers(self):
        try:
            message = self.messages.get_nowait()
        except queue.Empty:
            return
        raise ProtocolError('Display worker reported ' + message['kind'])

    def dispatch(self, route, *, expect_missing=None, allow_incomplete=False):
        now = datetime.now(timezone.utc)
        command = DisplayCommand.parse({'schema_version':1,'command_id':'cmd-'+uuid4().hex,
            'incident_id':route['incident_id'],'event_id':route['event_id'],'route_version':route['route_version'],
            'action':'DISPLAY_ROUTE' if route['target_exit'] else 'CLEAR_ROUTE','route_exit':route['target_exit'],
            'guidance_status':route['status'],'timestamp_utc':now.isoformat(),
            'expires_at_utc':(now+timedelta(seconds=self.settings.sensor_ttl)).isoformat(),
            'source':self.resources['namespace']+':controller','data_origin':'SYNTHETIC'},self.graph.exits)
        self.evidence.write('command-'+command.command_id+'.json',command.to_dict())
        fanout = fanout_command(self.controller,self.group,command,self.evidence)
        tracker = AckSet(command,[self.configs[r]['ae_id'] for r in ROLES],
                         sources={self.configs[r]['ae_id']:self.configs[r]['source'] for r in ROLES})
        deadline = time.monotonic() + self.settings.ack_timeout
        observed = {}
        while time.monotonic() < deadline:
            self.check_workers()
            for row in self.inbox.records():
                role = self.ack_refs.get(row['subscription_ref'])
                if role and tracker.add(row['event'],self.configs[role]['ae_id']):
                    observed[role] = row
            if not tracker.missing:
                break
            time.sleep(0.05)
        missing = {role for role in ROLES if self.configs[role]['ae_id'] in tracker.missing}
        if not allow_incomplete and missing != ({expect_missing} if expect_missing else set()):
            raise ProtocolError('ACK completion differs from the expected scenario')
        readbacks, states = {}, {}
        for role,row in observed.items():
            path = self.configs[role]['acks'] + '/' + ack_name(command.command_id)
            actual = self.controller.resource(self.controller.retrieve(path),4)
            content = strict_json(actual['con']) if isinstance(actual['con'],str) else actual['con']
            if actual['ri'] != row['cin_ri'] or content != row['event']:
                raise ProtocolError('ACK CIN read-back differs from actual callback')
            state = DisplayState.snapshot(self.configs[role]['state_path'])
            if state is None or state['command_id'] != command.command_id or state['route_exit'] != command.route_exit or state['guidance_status'] != command.guidance_status:
                raise ProtocolError('Device display state differs from its APPLIED ACK')
            readbacks[role], states[role] = {'path':path,'ri':actual['ri'],'ack':content}, state
        result = {'command':command.to_dict(),'state':'INCOMPLETE' if missing else 'ALL_ACKED',
                  'missing_devices':sorted(missing),'ack_count':len(readbacks),'acks':readbacks,'display_states':states,
                  'missing_display_states':{r:DisplayState.snapshot(self.configs[r]['state_path']) for r in missing},'fanout':fanout}
        self.results.append(result)
        self.evidence.append('delivery.jsonl',result)
        return result

    def stop_device(self, role):
        self.stops[role].set()
        self.processes[role].join(timeout=5)
        if self.processes[role].is_alive() or self.processes[role].exitcode != 0:
            raise ProtocolError('Stopped display did not exit cleanly')
        self.evidence.event(hop='display_stopped',role=role,pid=self.processes[role].pid)

    def close(self):
        clean = True
        for stop in self.stops.values():
            stop.set()
        for process in self.processes.values():
            if process.pid is None:
                continue
            process.join(timeout=5)
            if process.is_alive():
                clean = False
                process.terminate()
                process.join(timeout=2)
            clean = clean and process.exitcode == 0
        return clean
