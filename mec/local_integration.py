"""Local configured MEC discovery -> actual CSE catalog/reader/SUB/ACP gate.

This client is not a MEC platform, lifecycle implementation or official MEC-IPE.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import sys
from threading import Thread
import time
from urllib.parse import urlsplit
from uuid import uuid4

from backend.config import http_url, read_dotenv
from backend.evidence import Evidence, source_identity
from backend.notifications import NotificationService, NotificationStore, notification_server
from backend.p0 import IntegrationBlocked, probe, subscription_refs
from mec.catalog import CatalogSettings, MECUnavailable, discover, persist_catalog
from onem2m.client import CSEClient, CSEError, ProtocolError, TransportError, strict_json

ROOT = Path(__file__).resolve().parents[1]


def local_url(value, label, *, aliases=()):
    """Reject public/Hosted targets before any request in this local-only gate."""
    value = http_url(value, label)
    host = urlsplit(value).hostname
    if host in {'localhost', 'host.docker.internal', *aliases}:
        return value
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError('Local integration requires an explicit private host address') from None
    private = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', 'fc00::/7')]
    if not address.is_loopback and not any(address in network for network in private):
        raise ValueError('Public and Hosted addresses are excluded from this gate')
    return value


def configuration(env):
    value = env.get('MEC_LOCAL_SERVICE_MGMT_URL', '')
    if not value:
        raise IntegrationBlocked('MEC_LOCAL_SERVICE_MGMT_URL_NOT_CONFIGURED')
    # No credential is silently dropped by the private unauthenticated slice.
    if any(env.get(k) for k in ('MEC_API_TOKEN_FILE', 'MEC_CA_FILE', 'CSE_CLIENT_CERT', 'CSE_CLIENT_KEY', 'CSE_CA_FILE')):
        raise ValueError('Use the configured authenticated MEC/CSE profiles for those settings')
    settings = CatalogSettings(local_url(value, 'MEC_LOCAL_SERVICE_MGMT_URL', aliases=('mec-platform',)), 'local-sandbox',
                               env.get('MEC_APPLICATION_INSTANCE_ID', ''))
    if env.get('MEC_IN_COMPOSE') == '1':
        host = urlsplit(value).hostname
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == 'localhost'
        if loopback:
            raise ValueError('Use the explicit host mapping instead of container loopback')
    cse = local_url(env.get('MEC_LOCAL_CSE_URL', 'http://mec-cse:8080'), 'MEC_LOCAL_CSE_URL', aliases=('mec-cse',))
    callback = local_url(env.get('MEC_LOCAL_CALLBACK_URL', 'http://mec-check:8000/onem2m/notify'),
                         'MEC_LOCAL_CALLBACK_URL', aliases=('mec-check',))
    base = env.get('MEC_LOCAL_CSE_BASE', 'fire-route-dev')
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', base):
        raise ValueError('Invalid local CSEBase name')
    return settings, cse, callback, base


@dataclass(frozen=True)
class CatalogMessage:
    event_id: str
    document: dict

    def to_dict(self):
        return self.document


def catalog_decoder(expected):
    def decode(content):
        if (not isinstance(content, dict) or content != expected
                or not isinstance(content.get('event_id'), str)
                or not re.fullmatch('mec-[0-9a-f]{32}', content['event_id'])):
            raise ValueError('Notification does not match the observed catalog')
        return CatalogMessage(content['event_id'], content)
    return decode


def provision(client, base, callback):
    namespace = 'fr_mec_' + uuid4().hex[:16]
    parent = '/' + base
    labels = ['fire-route', 'namespace:' + namespace]
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')
    actors = {}
    for role in ('bridge', 'reader'):
        name = namespace + '__' + role
        attrs = {'rn': name, 'api': 'Nfire-route.mec-catalog', 'rr': role == 'reader',
                 'srv': [client.release], 'lbl': labels + ['role:mec-' + role], 'et': expiry}
        if role == 'reader':
            attrs['poa'] = [callback]
        actual = client.ensure(parent, 2, attrs, creator=client.for_actor('C', 'ae-registration'))
        actors[role] = {'ae_id': actual['aei'], 'ri': actual['ri'], 'path': parent + '/' + name}
    if actors['bridge']['ae_id'] == actors['reader']['ae_id']:
        raise ProtocolError('Distinct actual MEC bridge/reader AE IDs required')
    rules = [{'acor': [actors['bridge']['ae_id']], 'acop': 3},
             {'acor': [actors['reader']['ae_id']], 'acop': 2},
             {'acor': [actors['reader']['ae_id']], 'acop': 1, 'acod': [{'ty': 3, 'chty': [23]}]},
             {'acor': [client.originator], 'acop': 63}]
    policy = client.ensure(parent, 1, {'rn': namespace + '__catalog-policy', 'lbl': labels, 'et': expiry,
        'pv': {'acr': rules}, 'pvs': {'acr': [{'acor': [client.originator], 'acop': 63}]}})
    container = client.ensure(actors['bridge']['path'], 3, {'rn': 'catalog',
        'lbl': labels + ['fire-route:mec-catalog'], 'et': expiry, 'mni': 100, 'acpi': [policy['ri']]})
    return {'namespace': namespace, 'actors': actors, 'policy_ri': policy['ri'],
            'container_ri': container['ri'], 'container': actors['bridge']['path'] + '/catalog'}


def run(env):
    evidence = Evidence(Path(env.get('EVIDENCE_ROOT', 'evidence')))
    summary = {'test': 'LOCAL_MEC_CSE_CATALOG', 'state': 'NOT_RUN', 'Hosted': 'NOT_CONTACTED',
        'MEC': 'NOT_CONTACTED', 'CSE': 'NOT_CONTACTED', 'MEC_IPE': 'NOT_IMPLEMENTED',
        'platform_deployment': 'NOT_VERIFIED', 'risk_placement': 'NOT_VERIFIED',
        'callback_transport': 'PRIVATE_HTTP_NOT_TLS', 'video': 'OUT_OF_SCOPE'}
    checks = {}
    server = thread = None

    def check(name, passed):
        checks[name] = bool(passed)
        if not passed:
            raise ProtocolError('Local MEC/CSE check failed: ' + name)

    def phase(name):
        summary['phase'] = name
        print(json.dumps({'test': summary['test'], 'phase': name}), flush=True)

    try:
        phase('VALIDATE_LOCAL_CONFIGURATION')
        settings, cse_url, callback, base = configuration(env)
        if sys.version_info < (3, 11):
            raise IntegrationBlocked('USE_PYTHON_3_12_LOCAL_MEC_PROFILE')
        phase('ACTUAL_LOCAL_MEC_DISCOVERY')
        summary['MEC'] = 'ATTEMPTED'
        snapshot = discover(settings)
        evidence.write('catalog.json', snapshot)
        summary['MEC'] = 'DISCOVERY_HTTP_VERIFIED_ONLY'
        summary['service_count'] = snapshot['service_count']
        check('actual_HTTP_200_validated_catalog', snapshot['http_status'] == 200)
        phase('ACTUAL_ISOLATED_CSE_AND_AEs')
        client = CSEClient(cse_url, 'CAdmin', '4', evidence=evidence)
        summary['CSE'] = 'ATTEMPTED'
        cb = probe(client, base)
        check('actual_CSEBase_returned', cb['ty'] == 5)
        expected = {**snapshot, 'consumption_path': 'APPLICATION_AE_BRIDGE_NOT_MEC_IPE'}
        store = NotificationStore(evidence.path / 'notifications.sqlite3')
        service = NotificationService(store, cb['csi'], '4', frozenset(), evidence, decoder=catalog_decoder(expected))
        server = notification_server('0.0.0.0', 8000, service)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        resources = provision(client, base, callback)
        evidence.write('resources.json', resources)
        check('two_actual_distinct_AEs', len({v['ae_id'] for v in resources['actors'].values()}) == 2)
        bridge = client.for_actor(resources['actors']['bridge']['ae_id'], 'mec-catalog-writer')
        reader = client.for_actor(resources['actors']['reader']['ae_id'], 'mec-catalog-reader')
        phase('ACTUAL_SUBSCRIPTION_VERIFICATION')
        sub = reader.ensure(resources['container'], 23, {'rn': 'catalog-sub', 'nu': [callback],
            'enc': {'net': [3]}, 'nct': 1, 'lbl': ['fire-route'],
            'et': (datetime.now(timezone.utc) + timedelta(hours=1)).strftime('%Y%m%dT%H%M%S')})
        refs = subscription_refs(cb['csi'], resources['container'] + '/catalog-sub', sub)
        check('actual_CSE_subscription_verification', bool(store.verified_refs() & refs))
        service.approve(refs)
        phase('ACTUAL_CATALOG_CIN_AND_INDEPENDENT_READER')
        reference = persist_catalog(bridge, resources['container'], snapshot)
        evidence.write('catalog-CSE.json', reference)
        retrieved = reader.resource(reader.retrieve(reference['path']), 4)
        check('independent_reader_same_CIN_and_content', retrieved['ri'] == reference['cin_ri'] and strict_json(retrieved['con']) == expected)
        deadline = time.monotonic() + 15
        while not store.find(snapshot['event_id']) and time.monotonic() < deadline:
            time.sleep(.05)
        found = store.find(snapshot['event_id'])
        check('actual_catalog_subscription_event', len(found) == 1 and found[0]['cin_ri'] == reference['cin_ri'] and found[0]['event'] == expected)
        phase('ACTUAL_READER_WRITE_DENIAL')
        denied = False
        try:
            reader.create(resources['container'], 4, {'rn': 'forbidden-' + uuid4().hex,
                'cnf': 'application/json:0', 'con': '{}'})
        except CSEError as exc:
            denied = exc.http_status == 403 and exc.rsc == 4103 and not isinstance(exc, ProtocolError)
        check('reader_CIN_CREATE_denied_403_4103', denied)
        summary.update(state='PASS', phase='COMPLETE', CSE='CIN_READBACK_SUB_AND_ACP_VERIFIED', cin_ri=reference['cin_ri'])
    except (IntegrationBlocked, MECUnavailable, TransportError) as exc:
        summary.update(state='BLOCKED', reason=str(exc) if isinstance(exc, IntegrationBlocked) else type(exc).__name__)
    except Exception as exc:
        summary.update(state='FAIL', reason=type(exc).__name__)
        for name in ('http_status', 'rsc'):
            value = getattr(exc, name, None)
            if type(value) is int:
                summary[name] = value
    finally:
        if server is not None:
            if thread is not None and thread.is_alive():
                server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=3)
    summary.update(checks=len(checks), failed_checks=[k for k, v in checks.items() if not v])
    evidence.write('checks.json', checks)
    evidence.write('meta.json', source_identity(ROOT))
    evidence.write('summary.json', summary)
    return summary, evidence.path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', action='store_true')
    args = parser.parse_args()
    values = read_dotenv(Path('.env'))
    values.update(os.environ)
    if args.preflight:
        try:
            configuration({**values, 'MEC_IN_COMPOSE': '1'})
        except (ValueError, IntegrationBlocked):
            print(json.dumps({'test': 'LOCAL_MEC_CONFIGURATION', 'state': 'BLOCKED',
                              'reason': 'CONFIGURE_ACTUAL_PRIVATE_MEC_URL_WITHOUT_UNSUPPORTED_AUTH',
                              'Hosted': 'NOT_CONTACTED', 'MEC': 'NOT_CONTACTED'}))
            raise SystemExit(1)
        print(json.dumps({'test': 'LOCAL_MEC_CONFIGURATION', 'state': 'CONFIGURED_NOT_CONTACTED',
                          'Hosted': 'NOT_CONTACTED', 'MEC': 'NOT_CONTACTED'}))
        raise SystemExit(0)
    result, path = run(values)
    print(json.dumps({**result, 'evidence': str(path)}))
    raise SystemExit(0 if result['state'] == 'PASS' else 1)
