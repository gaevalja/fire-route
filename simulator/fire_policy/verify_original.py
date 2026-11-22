"""Check a FireRoute comparison report against the independent 0015 checkpoint."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from simulator.fire_policy.comparison import MODEL_ID, MODEL_SHA256
from simulator.fire_policy.rl_sim import ZONE_IDS


def verify(original_run, report):
    snapshot = original_run / 'source_snapshot'
    manifest = json.loads((original_run / 'manifest.json').read_bytes())
    checkpoint = original_run / 'model.zip'
    if (manifest['id'] != MODEL_ID or report['model_sha256'] != MODEL_SHA256
            or hashlib.sha256(checkpoint.read_bytes()).hexdigest() != MODEL_SHA256):
        raise ValueError('Expected the original FIRE_EVAC_0015 checkpoint')
    for name in ('rl_env.py', 'rl_sim.py', 'rl_config.py', 'scenario_pool.py'):
        if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != manifest['source_sha256'][name]:
            raise ValueError(f'Original snapshot checksum differs: {name}')

    # Use the archived environment and native MaskablePPO as the independent reference.
    sys.path.insert(0, str(snapshot.resolve()))
    import torch
    from rl_env import FireEvacEnv
    from sb3_contrib import MaskablePPO

    torch.set_num_threads(1)
    model = MaskablePPO.load(checkpoint, device='cpu', custom_objects={
        'learning_rate': 0.0003, 'lr_schedule': lambda _: 0.0003, 'clip_range': lambda _: 0.2,
    })
    mismatches = []
    limit = report['max_seconds']
    for case in report['cases']:
        env = FireEvacEnv(wind=case['wind_mps'])
        obs, info = env.reset(options={'scenario_seed': case['seed'], 'start_room': case['start_room']})
        actions = []
        position_at_limit = info['position']
        while info['outcome'] is None and info['second'] <= limit:
            action, _ = model.predict(obs, deterministic=True, action_masks=env.action_masks())
            action = int(action)
            actions.append((info['second'], info['position'], action))
            position_at_limit = ZONE_IDS[action] if action < len(ZONE_IDS) else info['position']
            obs, _, _, _, info = env.step(action)
        archived_outcome = ((info['outcome'], info['death_reason'], info['second'], info['position'])
                            if info['second'] <= limit else ('incomplete', None, None, position_at_limit))
        track = case['policies']['ppo']
        expected = (track['outcome'], track['reason'], track['finished_at'], track['position'])
        expected_actions = [(entry['second'], entry['origin'], entry['action_index']) for entry in track['decisions']]
        if archived_outcome != expected or actions != expected_actions:
            first = next((i for i, pair in enumerate(zip(actions, expected_actions)) if pair[0] != pair[1]), None)
            mismatches.append({'wind_mps': case['wind_mps'], 'seed': case['seed'], 'start_room': case['start_room'],
                               'native': archived_outcome, 'integrated': expected,
                               'first_action_mismatch': first, 'action_counts': [len(actions), len(expected_actions)]})
        env.close()
    return {'model_id': MODEL_ID, 'cases': len(report['cases']), 'mismatches': mismatches,
            'matching': len(report['cases']) - len(mismatches)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_run', type=Path)
    parser.add_argument('comparison_report', type=Path)
    args = parser.parse_args()
    result = verify(args.original_run, json.loads(args.comparison_report.read_bytes()))
    print(json.dumps(result))
    return int(bool(result['mismatches']))


if __name__ == '__main__':
    raise SystemExit(main())
