"""Actual GRP/fopt operations; an aggregate is never treated as device ACKs."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

from onem2m.client import CSEClient, ProtocolError, strict_json


def create_display_group(admin, controller, resources, retention_seconds):
    members = {role:resources['containers'][role + '/commands'] for role in ['display-a','display-b','display-c']}
    if len({c['ri'] for c in members.values()}) != 3:
        raise ProtocolError('Group requires three distinct actual command container IDs')
    expiry = (datetime.now(timezone.utc)+timedelta(seconds=retention_seconds)).strftime('%Y%m%dT%H%M%S')
    policy = admin.ensure(resources['actors']['controller']['path'].rsplit('/',1)[0], 1, {
        'rn':resources['namespace'] + '__group-policy', 'et':expiry, 'lbl':['fire-route','namespace:' + resources['namespace']],
        'pv':{'acr':[{'acor':[controller.originator], 'acop':3}, {'acor':[admin.originator], 'acop':63}]},
        'pvs':{'acr':[{'acor':[admin.originator], 'acop':63}]}})
    parent = resources['actors']['controller']['path']
    attrs = {'rn':'DisplayCommandGroup', 'mt':3, 'mnm':3, 'et':expiry,
             # Actual ACME CREATE canonicalizes local SP-relative member URIs to
             # CSE-relative IDs. Use the returned local CNT IDs from the start;
             # keep exact ensure/read-back checks rather than ignoring mid.
             'mid':[c['ri'] for c in members.values()],
             'acpi':[policy['ri']], 'lbl':['fire-route','namespace:' + resources['namespace']]}
    created = admin.ensure(parent, 9, attrs)
    path = parent + '/' + attrs['rn']
    actual = controller.resource(controller.retrieve(path), 9)
    if actual['ri'] != created['ri'] or actual.get('mt') != 3 or actual.get('cnm') != 3 or set(actual.get('mid',[])) != set(attrs['mid']):
        raise ProtocolError('Actual group identity/type/members differ')
    return {'path':path, 'ri':actual['ri'], 'resource':actual, 'members':members}


def member_cins(aggregate, expected_members):
    envelope = aggregate.get('m2m:agr') if isinstance(aggregate,dict) else None
    responses = envelope.get('m2m:rsp') if isinstance(envelope,dict) else None
    if not isinstance(responses,list) or len(responses) != len(expected_members):
        raise ProtocolError('Fan-out member count differs')
    result = {}
    for response in responses:
        if not isinstance(response,dict) or type(response.get('rsc')) is not int or response['rsc'] != 2001:
            raise ProtocolError('Fan-out contains a failed member CREATE')
        cin = CSEClient.resource(response.get('pc',{}), 4)
        parent = cin.get('pi')
        if not isinstance(parent,str) or parent not in expected_members or parent in result:
            raise ProtocolError('Fan-out contains an unknown/duplicate member')
        result[parent] = cin
    if len({c['ri'] for c in result.values()}) != len(expected_members):
        raise ProtocolError('Fan-out returned repeated CIN identities')
    return result


def fanout_command(client, group, command, evidence):
    name = 'command-' + hashlib.sha256(command.command_id.encode()).hexdigest()
    content = command.to_dict()
    aggregate = client.fanout_create(group['path'] + '/fopt', {
        'rn':name, 'cnf':'application/json:0',
        'con':json.dumps(content,sort_keys=True,separators=(',',':'),allow_nan=False)})
    created = member_cins(aggregate, {c['ri'] for c in group['members'].values()})
    records = {}
    for role, container in group['members'].items():
        actual = client.resource(client.retrieve(container['path'] + '/' + name), 4)
        data = strict_json(actual['con']) if isinstance(actual['con'],str) else actual['con']
        if actual['ri'] != created[container['ri']]['ri'] or actual.get('pi') != container['ri'] or data != content:
            raise ProtocolError('Fan-out CIN read-back differs at a member')
        records[role] = {'path':container['path'] + '/' + name, 'ri':actual['ri'], 'parent_ri':actual['pi']}
    result = {'command':content, 'group_ri':group['ri'], 'members':records}
    evidence.append('fanout.jsonl', result)
    return result
