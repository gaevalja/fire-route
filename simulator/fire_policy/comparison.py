"""Run both policies against the same sequence of current fire frames."""

from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from mec.risk.evacuation import Navigation
from simulator.fire_policy.rl_config import RULES
from simulator.fire_policy.rl_sim import FireSimulator, MOVE_NEIGHBORS, ROOM_IDS, ZONE_IDS, ZONE_TYPES


MODEL_ID = 'FIRE_EVAC_0015'
MODEL_SHA256 = 'd2b2a9f3066a1102655adfd2f8a5840b3a32acd7143db1cc3d0df08298a5db32'
ACTOR_SHA256 = 'd26485ee574f81636f53d240c65b98331c003245ec28189690f2330712a1d45a'
ZONE_INDEX = {zone: index for index, zone in enumerate(ZONE_IDS)}
OBSERVATION_DIM = len(ZONE_IDS) * 4 + 1
WAIT = len(ZONE_IDS)
EXIT = WAIT + 1
LOBBY = 'F1-L'
ASSETS = Path(__file__).resolve().with_name('assets')


@lru_cache(maxsize=1)
def load_actor():
    """Load the audited, deterministic actor export of the original checkpoint."""
    import numpy as np

    raw = (ASSETS / 'browser_policy.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != ACTOR_SHA256:
        raise ValueError('FIRE_EVAC_0015 actor export checksum differs')
    if hashlib.sha256((ASSETS / 'model.zip').read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError('FIRE_EVAC_0015 model checkpoint checksum differs')
    policy = json.loads(raw)
    if (policy['run'] != MODEL_ID or policy['sourceModelSha256'] != MODEL_SHA256
            or policy['observationDim'] != OBSERVATION_DIM or policy['actionCount'] != EXIT + 1
            or tuple(policy['zoneIds']) != ZONE_IDS or policy['activation'] != 'relu'):
        raise ValueError('FIRE_EVAC_0015 policy contract differs')
    layers = [(np.asarray(layer['weight'], dtype=np.float64), np.asarray(layer['bias'], dtype=np.float64))
              for layer in policy['layers']]
    dimensions = [(128, OBSERVATION_DIM), (128, 128), (EXIT + 1, 128)]
    if len(layers) != len(dimensions) or any(
            weight.shape != shape or bias.shape != (shape[0],)
            for (weight, bias), shape in zip(layers, dimensions)):
        raise ValueError('FIRE_EVAC_0015 actor layer dimensions differ')
    return layers


def observation(second, position, hazards):
    """Use the archive's per-zone feature order and float32 normalization."""
    import numpy as np

    values = np.empty(OBSERVATION_DIM, dtype=np.float32)
    for index, zone in enumerate(ZONE_IDS):
        state = hazards[zone]
        values[index * 4:index * 4 + 4] = (
            state['fire_index'] / 100, state['smoke_index'] / 100, state['collapsed'], position == zone)
    values[-1] = min(second / RULES.time_observation_scale, 1)
    return values


def action_mask(position, hazards):
    allowed = [False] * (EXIT + 1)
    allowed[WAIT] = True
    allowed[EXIT] = position == LOBBY
    for neighbor in MOVE_NEIGHBORS[position]:
        allowed[ZONE_INDEX[neighbor]] = not hazards[neighbor]['collapsed']
    return allowed


def ppo_action(second, position, hazards):
    import numpy as np

    values = observation(second, position, hazards)
    for index, (weight, bias) in enumerate(load_actor()):
        # Match the archived browser actor's double accumulation, then float32 output.
        values = np.einsum('ij,j->i', weight, values) + bias
        if index < 2:
            values = np.maximum(values, 0)
        values = values.astype(np.float32)
    mask = action_mask(position, hazards)
    return max((action for action in range(len(mask)) if mask[action]), key=values.__getitem__)


@dataclass
class Decision:
    second: int
    origin: str
    target: str
    action: str
    action_index: int
    duration_seconds: int
    route_available: bool


@dataclass
class Evacuee:
    position: str
    decision: Decision | None = None
    outcome: str | None = None
    reason: str | None = None
    finished_at: int | None = None

    def finish(self, outcome, second, reason=None):
        self.outcome = outcome
        self.reason = reason
        self.finished_at = second

    def snapshot(self):
        result = asdict(self)
        if self.outcome:
            result['status'] = 'FINISHED'
        elif self.decision is None:
            result['status'] = 'PRE_DEPARTURE'
        elif not self.decision.route_available:
            result['status'] = 'NO_ROUTE'
        else:
            result['status'] = self.decision.action.upper()
        return result


def death_reason(hazard):
    if hazard['collapsed']:
        return 'collapse'
    if hazard['fire_index'] >= RULES.fire_death_at:
        return 'fire'
    if hazard['smoke_index'] >= RULES.smoke_death_at:
        return 'smoke'
    return None


def rescue_kind(second, position, hazard):
    if position == 'F11-ROOF' and second >= RULES.roof_rescue_at:
        return 'roof'
    if (ZONE_TYPES[position] == 'room' and second >= RULES.room_rescue_at
            and hazard['fire_index'] <= RULES.room_rescue_fire_max):
        return 'room'
    return None


def movement_seconds(action, origin, target, hazards):
    if action != WAIT and any(
            hazards[zone]['fire_index'] > RULES.slow_move_fire_above
            or hazards[zone]['smoke_index'] > RULES.slow_move_smoke_above
            for zone in {origin, target} if zone in hazards):
        return RULES.slow_move_seconds
    return RULES.action_seconds


class Comparison:
    """Two independent residents starting at the same location and time.

    The 0015 environment moves to the selected zone immediately, locks the
    action's duration to that frame, and checks hazards on every subsequent
    second. Exit and rescue are evaluated on action completion, after death.
    """

    def __init__(self, start_room):
        if start_room not in ROOM_IDS:
            raise ValueError('The comparison start must be a fire_evac room')
        load_actor()
        self.start_room = start_room
        self.tracks = {policy: Evacuee(start_room) for policy in ('dijkstra', 'ppo')}

    def advance(self, second, navigation, *, ended=False):
        decisions = {}
        for policy, track in self.tracks.items():
            decision = self._advance_track(policy, track, second, navigation, ended)
            if decision is not None:
                decisions[policy] = decision
        return decisions

    def _advance_track(self, policy, track, second, navigation, ended):
        if track.outcome:
            return None
        hazards = navigation.hazards
        reason = death_reason(hazards[track.position])
        if reason:
            track.finish('death', second, reason)
            return None
        previous = track.decision
        if previous and second == previous.second + previous.duration_seconds:
            if previous.action_index == EXIT:
                track.position = 'EXIT'
                track.finish('exit', second)
                return None
            rescue = rescue_kind(second, track.position, hazards[track.position])
            if rescue:
                track.finish(rescue, second)
                return None
        if ended:
            track.finish('death', second, 'scenario_end')
            return None
        if second < RULES.awareness_seconds or (
                previous and second < previous.second + previous.duration_seconds):
            return None

        origin = track.position
        route_available = True
        if policy == 'ppo':
            action = ppo_action(second, origin, hazards)
        elif origin == LOBBY:
            action = EXIT
        else:
            path = navigation.route(origin)['path']
            route_available = bool(path)
            action = ZONE_INDEX[path[1]] if route_available else WAIT

        if action == WAIT:
            kind, target = 'wait', origin
        elif action == EXIT:
            kind, target = 'exit', 'EXIT'
        else:
            kind, target = 'move', ZONE_IDS[action]
            track.position = target
            reason = 'elevator' if ZONE_TYPES[target] == 'elevator' else death_reason(hazards[target])
            if reason:
                track.finish('death', second, reason)
        duration = movement_seconds(action, origin, target, hazards)
        track.decision = Decision(second, origin, target, kind, action, duration, route_available)
        return track.decision

    def snapshot(self):
        return {'model_id': MODEL_ID, 'model_sha256': MODEL_SHA256, 'start_room': self.start_room,
                'policies': {policy: track.snapshot() for policy, track in self.tracks.items()}}


def compare_case(seed, wind, room, max_seconds=12000, *, ignition_room=None, include_frames=False):
    """Run a single paired scenario for batch evaluation or synchronized playback."""
    simulator = FireSimulator(seed, wind, ignition_id=ignition_room)
    navigation = Navigation()
    comparison = Comparison(room)
    decisions = {name: [] for name in comparison.tracks}
    frames = []
    while True:
        second = simulator.second
        navigation.hazards = {zone: {'fire_index': state['fire'], 'smoke_index': state['smoke'],
                                    'collapsed': state['collapsed']}
                              for zone, state in simulator.zones.items()}
        updates = comparison.advance(second, navigation, ended=simulator.ended)
        for name, decision in updates.items():
            decisions[name].append(asdict(decision))

        tracks = comparison.tracks.values()
        done = simulator.ended or second >= max_seconds or all(track.outcome for track in tracks)
        if include_frames and (done or updates or second % 30 == 0
                               or any(track.finished_at == second for track in tracks)):
            frames.append({
                'second': second,
                'zones': {zone: {'fire': round(state['fire'], 3), 'smoke': round(state['smoke'], 3),
                                 'collapsed': state['collapsed']}
                          for zone, state in simulator.zones.items()},
                'policies': {name: track.snapshot() for name, track in comparison.tracks.items()},
            })
        if done:
            break
        simulator.step_seconds()

    policies = comparison.snapshot()['policies']
    for name, state in policies.items():
        state['decisions'] = decisions[name]
        if state['outcome'] is None:
            state['outcome'] = 'incomplete'
    result = {'seed': seed, 'wind_mps': wind, 'start_room': room,
              'ignition_room': simulator.ignition_id, 'policies': policies}
    if include_frames:
        result.update(model_id=MODEL_ID, model_sha256=MODEL_SHA256, frames=frames, rules={
            'awareness_seconds': RULES.awareness_seconds,
            'action_seconds': RULES.action_seconds,
            'slow_move_seconds': RULES.slow_move_seconds,
            'fire_death_at': RULES.fire_death_at,
            'smoke_death_at': RULES.smoke_death_at,
            'roof_rescue_at': RULES.roof_rescue_at,
            'room_rescue_at': RULES.room_rescue_at,
            'room_rescue_fire_max': RULES.room_rescue_fire_max,
            'dijkstra_fire_block': navigation.assumptions['fire_block_index'],
            'dijkstra_smoke_block': navigation.assumptions['smoke_block_index'],
            'dijkstra_policy_sha256': navigation.policy_hash,
        })
    return result
