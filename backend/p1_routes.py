"""Actual-CSE P1 route-persistence slice; Group/ACK/UI/MEC are separate gates."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import socket
import sys
from threading import Thread
import time
from uuid import uuid4

from backend.config import ConfigurationError, Settings
from backend.evidence import Evidence, source_identity
from backend.incidents import IncidentStore
from backend.notifications import NotificationService, NotificationStore, notification_server
from backend.p0 import IntegrationBlocked, default_fixture, subscription_refs, wait_for_cse
from mec.risk.routing import BuildingGraph
from onem2m.bootstrap import bootstrap
from onem2m.client import CSEClient, CSEError, ProtocolError, strict_json
from onem2m.decisions import publish_pending
from simulator.events import SensorEvent, synthetic_smoke, utc_now

ROOT = Path(__file__).resolve().parents[1]


def require_denial(operation) -> None:
    try:
        operation()
    except CSEError as exc:
        if not isinstance(exc, ProtocolError) and exc.rsc == 4103 and exc.http_status == 403:
            return
        raise
    raise ProtocolError("Actual CSE allowed a forbidden P1 operation")


def run(settings: Settings, *, require_target_python: bool = True, with_displays: bool = False) -> tuple[dict, Path]:
    evidence = Evidence(settings.evidence_root, secret_values=(settings.admin_originator,))
    namespace = 'fr_' + uuid4().hex[:16]
    summary = {'test': 'P1_ROUTES', 'state': 'NOT_RUN', 'pass': 0, 'fail': 0, 'blocked': 0,
               'Group': 'NOT_RUN', 'all_device_acks': 'NOT_RUN', 'UI': 'NOT_RUN',
               'MEC': 'unavailable', 'latency_samples': 0}
    if with_displays:
        summary['test'] = 'P1_GROUP'
    metadata = {'started_at_utc': utc_now(), 'phase': 'P1_ROUTE_PERSISTENCE_ONLY', 'test': 'P1_ROUTES',
                'namespace': namespace, 'python': platform.python_version(), 'settings': settings.public(),
                'deployment_option': 'standalone_dev_CSE_NOT_MEC', 'real_CSE': False,
                'real_MEC': False, 'input': 'SYNTHETIC', **source_identity(ROOT)}
    if with_displays:
        metadata.update(phase='P1_GROUP_DEVICE_SLICE', test='P1_GROUP')
    server = worker = delivery = None
    evidence.write('meta.json', metadata)
    try:
        if require_target_python and sys.version_info < (3, 11):
            raise IntegrationBlocked('Product runtime requires Python >=3.11; use the Python 3.12 Compose profile')
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM):
                pass
        except OSError as exc:
            raise IntegrationBlocked('Runtime denies network socket creation; actual P1 test cannot run') from exc
        if settings.runtime_info:
            if not settings.runtime_info.is_file():
                raise IntegrationBlocked('Actual CSE runtime metadata unavailable')
            metadata['observed_cse_runtime'] = strict_json(settings.runtime_info.read_bytes())
        graph = BuildingGraph.load(default_fixture())
        admin = CSEClient(settings.cse_url, settings.admin_originator, settings.release,
                          timeout=settings.request_timeout, evidence=evidence)
        cb = wait_for_cse(admin, settings)
        metadata.update(real_CSE=True, actual_cse_base=cb)
        evidence.write('meta.json', metadata)
        notifications = NotificationStore(evidence.path / 'notification-state.sqlite3')
        service = NotificationService(notifications, cb['csi'], settings.release, graph.nodes, evidence)
        try:
            server = notification_server(settings.bind_host, settings.bind_port, service)
        except OSError as exc:
            raise IntegrationBlocked('P1 notification listener unavailable') from exc
        worker = Thread(target=server.serve_forever, name='fireroute-p1-notifications', daemon=True)
        worker.start()
        callbacks = None
        if with_displays:
            from backend.delivery import display_callbacks
            callbacks = display_callbacks(settings)
            if 9 not in cb.get('srt', []):
                raise ProtocolError('Actual CSE does not advertise Group support')
        resources = bootstrap(admin, settings.cse_base, namespace, settings.notification_url,
                              settings.retention_seconds, decision_policies=True, display_callbacks=callbacks)
        evidence.write('resources.json', resources)
        controller = admin.for_actor(resources['actors']['controller']['ae_id'], 'controller')
        sensor = admin.for_actor(resources['actors']['sensor']['ae_id'], 'sensor')
        telemetry = resources['containers']['sensor/telemetry']['path']
        sub = controller.ensure(telemetry, 23, {'rn': 'controller-sub', 'nu': [settings.notification_url],
                    'enc': {'net': [3]}, 'nct': 1, 'lbl': ['fire-route', 'namespace:' + namespace]})
        refs = subscription_refs(cb['csi'], telemetry + '/controller-sub', sub)
        if not notifications.verified_refs() & refs:
            raise ProtocolError('P1 SUB verification callback missing')
        service.approve(refs)
        actual_sub = controller.resource(controller.retrieve(telemetry + '/controller-sub'), 23)
        if actual_sub['ri'] != sub['ri']:
            raise ProtocolError('P1 SUB read-back differs')
        store = IncidentStore(evidence.path / 'incident-state.sqlite3', graph, namespace + ':controller',
                              sensor_ttl=settings.sensor_ttl, max_clock_skew=settings.max_clock_skew)
        template = synthetic_smoke(graph.nodes, namespace)
        if with_displays:
            from backend.delivery import DeliverySession
            delivery = DeliverySession(settings,admin,controller,resources,cb,service,notifications,graph,template.incident_id,evidence)
            delivery.start()

        def observe(event: SensorEvent) -> SensorEvent:
            name = 'event-' + uuid4().hex
            evidence.event(hop='sensor_generated', **event.to_dict())
            cin = sensor.resource(sensor.create(telemetry, 4, {'rn': name, 'cnf': 'application/json:0',
                        'con': json.dumps(event.to_dict(), sort_keys=True, separators=(',', ':'))}), 4)
            read = sensor.resource(sensor.retrieve(telemetry + '/' + name), 4)
            content = strict_json(read['con']) if isinstance(read['con'], str) else read['con']
            if read['ri'] != cin['ri'] or content != event.to_dict():
                raise ProtocolError('P1 telemetry CIN read-back differs')
            deadline = time.monotonic() + settings.notification_timeout
            while not notifications.find(event.event_id) and time.monotonic() < deadline:
                time.sleep(0.05)
            rows = notifications.find(event.event_id)
            if len(rows) != 1 or rows[0]['cin_ri'] != cin['ri'] or rows[0]['event'] != content:
                raise ProtocolError('P1 actual durable notification missing or mismatched')
            return SensorEvent.parse(rows[0]['event'], graph.nodes)

        results = []
        cases = [('baseline', 'F3_ROOM1', 'temperature_celsius', 'degC', 22.5, 1, 'EXIT_A', 13),
                 ('fire_a', 'F2_A', 'synthetic_smoke_index', 'unitless_0_100', 90, 2, 'EXIT_B', 16),
                 ('no_route', 'F2_B', 'synthetic_smoke_index', 'unitless_0_100', 90, 1, None, None)]
        if with_displays:
            cases.append(('missing_display', 'F3_ROOM1', 'temperature_celsius', 'degC', 22.5, 2, None, None))
        accepted = []
        for index, (case, node, sensor_type, unit, value, sequence, exit_id, cost) in enumerate(cases, 1):
            if case == 'missing_display':
                delivery.stop_device('display-c')
            event = replace(template, event_id='e-' + uuid4().hex, sensor_id=sensor_type + ':' + node,
                            location_node=node, sensor_type=sensor_type, unit=unit, value=value,
                            sequence=sequence, timestamp_utc=utc_now())
            actual_event = observe(event)
            update = store.accept(actual_event)
            if update['state'] != 'ACCEPTED':
                raise ProtocolError('P1 new scenario event was not accepted')
            records = publish_pending(store, controller, resources['containers'], evidence)
            if len(records) != 1:
                raise ProtocolError('P1 expected exactly one persisted decision pair')
            route = records[0]['route']['content']
            expected_status = 'ROUTE_AVAILABLE' if exit_id else 'NO_VERIFIED_ROUTE'
            if (route['route_version'] != index or route['event_id'] != actual_event.event_id
                    or route['incident_id'] != actual_event.incident_id or route['target_exit'] != exit_id
                    or route['routing_cost'] != cost or route['status'] != expected_status
                    or (case != 'baseline' and 'F2_A' in route['path'])
                    or (case == 'no_route' and route['path'] != [])):
                raise ProtocolError('Computed actual route CIN does not satisfy the scenario')
            results.append({'scenario': case, **records[0]})
            accepted.append(actual_event)
            if delivery:
                delivery.dispatch(route,expect_missing='display-c' if case == 'missing_display' else None)
        duplicate = store.accept(accepted[-1])
        if duplicate['state'] != 'DUPLICATE' or publish_pending(store, controller, resources['containers'], evidence):
            raise ProtocolError('Duplicate sensor event generated another route')
        old = replace(accepted[1], event_id='e-' + uuid4().hex, sequence=1, value=0, timestamp_utc=utc_now())
        if store.accept(observe(old))['state'] != 'IGNORED_OUTDATED' or store.pending():
            raise ProtocolError('Outdated actual sensor event changed the route outbox')
        route_parent = resources['containers']['controller/routes']['path']
        require_denial(lambda: sensor.create(route_parent, 4, {'rn': 'forbidden-' + uuid4().hex, 'con': '{}'}))
        resident = admin.for_actor(resources['actors']['resident']['ae_id'], 'resident')
        require_denial(lambda: resident.retrieve(resources['containers']['controller/hazards']['path']))
        resident_route = resident.resource(resident.retrieve(results[-1]['route']['path']), 4)
        if resident_route['ri'] != results[-1]['route']['ri']:
            raise ProtocolError('Resident authorized route read differs')
        device_assertions = {}
        if delivery:
            require_denial(lambda: controller.create(resources['containers']['display-a/acks']['path'],4,{'con':'{}'}))
            device_a = admin.for_actor(resources['actors']['display-a']['ae_id'],'display-a-negative-test')
            require_denial(lambda: device_a.create(resources['containers']['display-a/commands']['path'],4,{'con':'{}'}))
            require_denial(lambda: device_a.create(resources['containers']['display-b/acks']['path'],4,{'con':'{}'}))
            require_denial(lambda: resident.fanout_create(delivery.group['path']+'/fopt',{'con':'{}'}))
            device_assertions = {'deliveries':delivery.results, 'independent_processes':delivery.ready,
                'controller_ACK_forgery_denied':True, 'device_command_write_denied':True,
                'cross_device_ACK_write_denied':True, 'resident_fanout_denied':True}
            if not delivery.close():
                raise ProtocolError('Independent display cleanup was not graceful')
            # Joining the processes flushes late worker errors into the queue.
            delivery.check_workers()
        evidence.write('assertions.json', {'SUB_verification': True, 'actual_notified_events': len(cases)+1,
                    'computed_actual_route_CINs': results, 'duplicate_did_not_create_route': True,
                    'outdated_actual_event_ignored': True, 'sensor_route_write_denied': True,
                    'resident_hazard_read_denied': True, 'resident_route_read_allowed': True, **device_assertions})
        summary.update(state='PASS', **{'pass': 1}, scenarios=len(cases), route_cins=len(cases), hazard_cins=len(cases),
                       actual_notified_events=len(cases)+1, incident_id=template.incident_id,
                       duplicate='PASS', outdated='PASS', baseline_ACP='PASS')
        if delivery:
            summary.update(Group='PASS', all_device_acks='3_COMPLETE_SCENARIOS',
                complete_deliveries=sum(x['state']=='ALL_ACKED' for x in delivery.results),
                expected_incomplete_deliveries=sum(x['state']=='INCOMPLETE' for x in delivery.results),
                command_cins=sum(len(x['fanout']['members']) for x in delivery.results),
                observed_device_ACKs=sum(x['ack_count'] for x in delivery.results), stopped_device='display-c',
                no_route_clears_displays='PASS', device_ACP_denials='PASS')
    except IntegrationBlocked as exc:
        summary.update(state='BLOCKED', blocked=1, reason=str(exc))
    except Exception as exc:
        summary.update(state='FAIL', fail=1, reason=str(exc) if isinstance(exc, CSEError) else type(exc).__name__)
    finally:
        if delivery:
            delivery.close()
        if server:
            server.shutdown()
            server.server_close()
            if worker:
                worker.join(timeout=5)
        evidence.write('summary.json', summary)
    return summary, evidence.path


def main(*, with_displays: bool = False) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path)
    args = parser.parse_args()
    try:
        settings = Settings.load()
        if args.evidence_root:
            settings = replace(settings, evidence_root=args.evidence_root)
        summary, path = run(settings, with_displays=with_displays)
    except (ConfigurationError, ValueError) as exc:
        print(json.dumps({'state': 'BLOCKED', 'reason': str(exc)}))
        return 2
    output = json.dumps({'evidence': str(path), **summary}, sort_keys=True)
    (path / 'tests.txt').write_text('command: ' + json.dumps(sys.orig_argv) + '\n' + output + '\n')
    print(output)
    return {'PASS': 0, 'FAIL': 1, 'BLOCKED': 2}[summary['state']]


if __name__ == '__main__':
    raise SystemExit(main())
