"""Frozen synthetic observation and named-CIN reconciliation, without POST retries."""
from copy import deepcopy
from datetime import datetime,timezone
import json

from onem2m.client import CSEError,ProtocolError,ResourceConflict,strict_json
from simulator.commands import utc_time
from simulator.scenario_frames import emission,validate_raw


class PendingInput:
    def __init__(self,raw,incident,source,bundle_hash):
        self.raw=deepcopy(validate_raw(raw,bundle_hash))
        self.incident,self.source,self.bundle_hash=incident,source,bundle_hash
        self.frame=emission(self.raw,incident,source,bundle_hash)

    def matches(self,raw):
        return self.raw==raw

    def deliver(self,client,parent,settings,evidence):
        """Read the exact name first; only a real NOT_FOUND permits CREATE."""
        name='frame-'+str(self.frame.data['sequence']);path=parent+'/'+name
        try:
            current=client.resource(client.retrieve(path),4)
        except CSEError as exc:
            if isinstance(exc,ProtocolError) or exc.http_status!=404 or exc.rsc!=4004:raise
            # A synthetic trace row can be sampled again only after the actual
            # CSE proves its old named observation absent. Never restamp a CIN.
            age=(datetime.now(timezone.utc)-utc_time(self.frame.data['timestamp_utc'])).total_seconds()
            if age>=settings.sensor_ttl:
                previous=self.frame
                self.frame=emission(self.raw,self.incident,self.source,self.bundle_hash)
                evidence.append('source-recovery.jsonl',{'state':'RESAMPLED_ABSENT_SYNTHETIC_INPUT',
                    'previous_event_id':previous.event_id,'previous_timestamp_utc':previous.data['timestamp_utc'],
                    'event_id':self.frame.event_id,'timestamp_utc':self.frame.data['timestamp_utc'],
                    'sequence':self.frame.data['sequence'],'path':path,'actual_http_status':404,'actual_rsc':4004})
            attrs={'rn':name,'cnf':'application/json:0','con':json.dumps(self.frame.to_dict(),separators=(',',':'))}
            try:current=client.resource(client.create(parent,4,attrs),4)
            except CSEError as conflict:
                if isinstance(conflict,ProtocolError) or conflict.http_status!=409 or conflict.rsc!=4105:raise
                current=client.resource(client.retrieve(path),4)
        actual=client.resource(client.retrieve(path),4)
        if (current['ri']!=actual['ri'] or actual.get('rn')!=name or actual.get('cnf')!='application/json:0'
                or strict_json(actual['con'])!=self.frame.to_dict()):
            raise ResourceConflict('Named scenario observation differs; never overwritten')
        age=(datetime.now(timezone.utc)-utc_time(self.frame.data['timestamp_utc'])).total_seconds()
        if age>=settings.sensor_ttl:
            raise ProtocolError('Stored scenario observation expired; explicit incident reset required')
        return self.frame,actual
