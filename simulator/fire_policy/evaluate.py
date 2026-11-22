"""Evaluate Dijkstra and FIRE_EVAC_0015 on paired fire scenarios."""

import argparse
from collections import Counter
import json
from pathlib import Path

from simulator.fire_policy.comparison import MODEL_ID, MODEL_SHA256, compare_case
from simulator.fire_policy.rl_config import RULES, evaluation_scenario_seed, evaluation_start_room
from simulator.fire_policy.rl_sim import ROOM_IDS, WIND_OPTIONS
from simulator.scenario_frames import source_manifest


OUTCOMES = ('exit', 'roof', 'room', 'death', 'incomplete')


def run(episodes, seed_base, max_seconds, winds=WIND_OPTIONS):
    report = {'model_id': MODEL_ID, 'model_sha256': MODEL_SHA256,
              'source_sha256': source_manifest()['bundle_sha256'], 'seed_base': seed_base,
              'episodes_per_wind': episodes, 'max_seconds': max_seconds,
              'awareness_seconds': RULES.awareness_seconds, 'cases': [], 'by_wind': {}}
    for wind in winds:
        counts = {name: Counter({kind: 0 for kind in OUTCOMES}) for name in ('dijkstra', 'ppo')}
        for offset in range(episodes):
            seed = evaluation_scenario_seed(offset, seed_base)
            case = compare_case(seed, wind, evaluation_start_room(seed, ROOM_IDS), max_seconds)
            report['cases'].append(case)
            for name, track in case['policies'].items():
                counts[name][track['outcome']] += 1
        report['by_wind'][str(wind)] = counts
        print(json.dumps({'wind_mps': wind, 'outcomes': counts}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episodes', type=int, default=200, help='paired cases per wind')
    parser.add_argument('--seed-base', type=int, default=2_000_000_000)
    parser.add_argument('--max-seconds', type=int, default=12000)
    parser.add_argument('--output', type=Path, default=Path('.runtime/fire-evac-comparison.json'))
    args = parser.parse_args()
    if args.episodes < 1 or args.max_seconds < 1:
        parser.error('episodes and max-seconds must be positive')
    result = run(args.episodes, args.seed_base, args.max_seconds)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.tmp')
    temporary.write_text(json.dumps(result, separators=(',', ':')) + '\n', encoding='utf-8')
    temporary.replace(output)
    print(output)


if __name__ == '__main__':
    main()
