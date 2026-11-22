"""Optional authenticated dashboard that requires real project-IPE risk results."""
from datetime import datetime, timezone
from pathlib import Path

from backend.scenario_core import ScenarioSession
from backend.scenario_demo import ScenarioApp, main as serve
from mec.interworking.client import Requester, VerifiedRemoteSnapshot, verified_estimate, verified_result
from onem2m.client import ProtocolError, strict_json
from simulator.commands import utc_time


class MecSession(ScenarioSession):
    def __init__(self,settings):
        super().__init__(settings);self.requester=None;self.remote=None;self.connection=None

    def access_readers(self):
        # The project IPE retrieves referenced access CINs with its own AE identity.
        return [self.connection['actors']['ipe']['ae_id']]

    def start(self):
        self.connection=connection=strict_json(Path('/ipe-state/connection.json').read_bytes())
        self.access_sensing={'occupancy-requests','occupancy-results'}<=set(connection['containers'])
        super().start()
        self.registration=connection['registration']
        self.requester=Requester(self.admin,connection,self.evidence,
            'http://mec-dashboard:8010/onem2m/notify',8010)
        self.requester.start()
        metadata=strict_json((self.evidence.path/'meta.json').read_bytes())
        metadata.update(real_MEC=False,MEC='AWAITING_VERIFIED_RESULT',
            deployment_option='LOCAL_EXTERNAL_COMPOSE_APP_REGISTERED_WITH_MEC',
            interworking='FIREROUTE_PROJECT_IPE_V1',ipe_evidence=connection['evidence'],
            occupancy_estimate='MEC_OCCUPANCY_SERVICE' if self.requester.occupancy_enabled else 'UNAVAILABLE',
            access_discovery=self.access_discovery)
        self.evidence.write('meta.json',metadata)

    def consume_received(self,frame,cin_ri):
        receipt=super().consume_received(frame,cin_ri)
        if receipt.state=='ACCEPTED':
            self.remote=None
            try:
                reply=self.requester.submit(frame.to_dict())
                if reply.get('service_id')!=self.registration['service_id']:raise ProtocolError('MEC service identity differs')
                verified_result(reply,frame.to_dict(),self.model.snapshot())
                self.remote=reply
                if self.frames==1:
                    metadata=strict_json((self.evidence.path/'meta.json').read_bytes())
                    metadata.update(real_MEC=True,MEC='VERIFIED_RESULT',app_id=reply['app_id'],service_id=reply['service_id'])
                    self.evidence.write('meta.json',metadata)
            except Exception:
                # Source may already be committed. Do not use the source-only
                # retry path or silently fall back to local decisions.
                raise ProtocolError('MEC computation incomplete; explicit incident reset required') from None
        return receipt

    def estimate_occupancy(self,references):
        if not self.requester or not self.requester.occupancy_enabled:return None
        reply=self.requester.submit_occupancy(references)
        estimate=verified_estimate(reply,references[-1],self.model.navigation)
        return estimate,{'computed_by':'MEC_OCCUPANCY_SERVICE','service_id':reply['service_id'],'app_id':reply['app_id'],
            'estimate_sha256':reply['estimate_sha256'],'request_cin':reply['request_cin'],'result_cin':reply['result_cin']}

    def publish(self):
        if self.remote is None:raise ProtocolError('No verified MEC decision')
        model=self.model;result=verified_result(self.remote,model.last,model.snapshot())
        try:
            self.model=VerifiedRemoteSnapshot(model,result)
            output=super().publish()
        finally:self.model=model
        self.evidence.append('mec-publication.jsonl',{'service_id':self.remote['service_id'],
            'event_id':result['event_id'],'route_version':result['route_version'],
            'result_sha256':self.remote['result_sha256']})
        return output

    def close(self):
        try:
            observer_clean=self.requester.close() if self.requester else True
        finally:
            devices_clean=super().close()
        return devices_clean and observer_clean


class MecScenarioApp(ScenarioApp):
    def __init__(self,settings,trace):super().__init__(settings,trace,session_factory=MecSession)

    def status(self):
        result=super().status();context=self.context
        reply=context.remote if context and hasattr(context,'remote') else None
        good=(reply and result['state']=='READY' and not result['busy']
              and datetime.now(timezone.utc)<utc_time(reply['valid_until_utc']))
        result.update(MEC='VERIFIED_RESULT' if good else 'UNKNOWN',interworking='FIREROUTE_PROJECT_IPE_V1')
        return result

    def view(self,incident,role,*,diagnostics=False,zone=None):
        result=super().view(incident,role,diagnostics=diagnostics,zone=zone)
        context=self.context;reply=context.remote if context else None
        verified=(reply and self.state=='READY' and not self.busy
            and result.get('route_version')==reply.get('sequence')
            and result.get('event_id',reply['source_event_id'])==reply['source_event_id']
            and datetime.now(timezone.utc)<utc_time(reply['valid_until_utc']))
        result['connections']['mec']='VERIFIED_RESULT' if verified else 'UNKNOWN'
        result['deployment_option']='LOCAL_EXTERNAL_COMPOSE_APP_REGISTERED_WITH_MEC'
        return result


if __name__=='__main__':raise SystemExit(serve(app_type=MecScenarioApp))
