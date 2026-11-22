"""Live observation acceptance; independent of CSE transport and pure model replay."""
from dataclasses import dataclass
from datetime import datetime,timezone

from simulator.commands import utc_time
from simulator.evacuation import FrameOrderError
from simulator.scenario_frames import ScenarioFrame


@dataclass(frozen=True)
class IngestionResult:
    state: str
    reason: str


def accept_live_frame(model,frame,settings,expected_hash,*,now=None):
    # Revalidate even a directly constructed dataclass; never mutate on rejection.
    frame=ScenarioFrame.parse(frame.to_dict(),expected_hash)
    data=frame.to_dict()
    if model.last==data:
        return IngestionResult('DUPLICATE','EXACT_REPLAY')
    current=datetime.now(timezone.utc) if now is None else now
    if current.utcoffset() is None or current.utcoffset().total_seconds()!=0:
        raise ValueError('Live ingestion clock must use UTC')
    stamp=utc_time(data['timestamp_utc']);age=(current-stamp).total_seconds()
    if age>=settings.sensor_ttl:return IngestionResult('REJECTED','EXPIRED')
    if age < -settings.max_clock_skew:return IngestionResult('REJECTED','FUTURE')
    if model.last is not None and stamp<utc_time(model.last['timestamp_utc']):
        return IngestionResult('REJECTED','TIMESTAMP_REGRESSION')
    try:
        accepted=model.accept(frame)
    except FrameOrderError:
        return IngestionResult('REJECTED','ORDER_OR_CONTEXT')
    return IngestionResult('ACCEPTED' if accepted else 'DUPLICATE','NEXT_FRAME' if accepted else 'EXACT_REPLAY')
