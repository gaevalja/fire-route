"""Model replay assets and paired scenarios for the ten-floor dashboard."""

import os
from pathlib import Path
import re
import sys

from onem2m.client import strict_json
from simulator.fire_policy.comparison import ASSETS, MODEL_ID, compare_case
from simulator.fire_policy.rl_config import evaluation_start_room
from simulator.fire_policy.rl_sim import ROOM_IDS, WIND_OPTIONS
from simulator.scenario_frames import ROOT


REPLAY_PAGE = '/model-replay/replay.html'
REPLAY_PREFIX = '/model-replay/'
COMPARE_PATH = REPLAY_PREFIX + 'compare'
MAKER_PREFIX = '/simulator/scenarios/fire_evac/'
RUN_ID = re.compile(r'FIRE_EVAC_[0-9]{4,}')
HTML = 'text/html; charset=utf-8'
SCRIPT = 'text/javascript; charset=utf-8'
CSS = 'text/css; charset=utf-8'
REPLAY_FILES = {'replay.html': HTML, 'replay.js': SCRIPT, 'offline_replay.js': SCRIPT, 'replay.css': CSS}
MAKER_FILES = {'index.html': HTML, 'config.js': SCRIPT, 'engine.js': SCRIPT, 'app.js': SCRIPT, 'styles.css': CSS}
RUN_FILES = {'browser_policy.json': 'application/json; charset=utf-8',
             'progress.csv': 'text/csv; charset=utf-8', 'eval_progress.csv': 'text/csv; charset=utf-8'}


def run_file(directory, name):
    path = directory / name
    if not path.is_symlink() and path.is_file():
        return path
    return None


class ModelReplay:
    def __init__(self, static_root, runs=None):
        self.static_root = static_root / 'model-replay'
        self.maker_root = ROOT / 'simulator/scenarios/fire_evac'
        if not self.maker_root.is_dir():
            self.maker_root = Path(sys.prefix) / 'share/fire-route/scenarios/fire_evac'
        self.runs = runs

    @classmethod
    def configured(cls, static_root):
        configured = os.getenv('FIRE_EVAC_RUNS_DIR')
        nearby = ROOT.parent / 'fire_evac/runs'
        runs = Path(configured) if configured else nearby if nearby.is_dir() else None
        return cls(static_root, runs)

    def run_directory(self, run):
        if self.runs is not None:
            path = self.runs / run
            if not path.is_symlink() and path.is_dir() and run_file(path, 'manifest.json'):
                return path
        return ASSETS if run == MODEL_ID else None

    def catalog(self):
        run_ids = {MODEL_ID}
        if self.runs is not None:
            try:
                run_ids.update(path.name for path in self.runs.iterdir() if RUN_ID.fullmatch(path.name))
            except OSError:
                pass  # The demo also runs with just its packaged model.
        runs = []
        for run in sorted(run_ids, key=lambda value: (int(value.split('_')[-1]), value), reverse=True):
            directory = self.run_directory(run)
            manifest = run_file(directory, 'manifest.json') if directory is not None else None
            if manifest is None:
                continue
            try:
                data = strict_json(manifest.read_bytes())
                if not isinstance(data, dict):
                    continue
                rules = data.get('evacuation_rules') or {}
                runs.append({
                    'id': run, 'status': data.get('status'), 'created_at': data.get('created_at'),
                    'training_wind': data.get('training_wind', 5),
                    'awareness_seconds': rules.get('awareness_seconds', 60),
                    'description': data.get('description', data.get('feature_set', '')),
                    'has_model': run_file(directory, 'browser_policy.json') is not None,
                })
            except (OSError, ValueError, AttributeError):
                continue
        return {'runs': runs}

    def compare(self, settings):
        if not {'seed', 'wind'} <= settings.keys() <= {'seed', 'wind', 'start_room', 'ignition_room'}:
            raise ValueError('시나리오 입력 항목을 확인해 주세요.')
        seed, wind = settings['seed'], settings['wind']
        if type(seed) is not int or not 1 <= seed <= 2**32 - 1:
            raise ValueError('시나리오 번호는 1부터 4,294,967,295까지의 정수여야 합니다.')
        if type(wind) is not int or wind not in WIND_OPTIONS:
            raise ValueError('풍속은 1·5·10·15 m/s 중 하나여야 합니다.')
        start = settings.get('start_room', '')
        ignition = settings.get('ignition_room', '')
        if any(not isinstance(room, str) or room and room not in ROOM_IDS for room in (start, ignition)):
            raise ValueError('시작 위치와 발화 위치는 건물의 방이어야 합니다.')
        return compare_case(seed, wind, start or evaluation_start_room(seed, ROOM_IDS),
                            ignition_room=ignition or None, include_frames=True)

    def asset(self, path):
        if path.startswith(MAKER_PREFIX):
            name = path.removeprefix(MAKER_PREFIX)
            if name in MAKER_FILES:
                return self.maker_root / name, MAKER_FILES[name]
            return None
        name = path.removeprefix(REPLAY_PREFIX)
        if name in REPLAY_FILES:
            return self.static_root / name, REPLAY_FILES[name]
        parts = name.split('/')
        if len(parts) == 3 and parts[0] == 'runs' and RUN_ID.fullmatch(parts[1]) and parts[2] in RUN_FILES:
            _, run, filename = parts
            directory = self.run_directory(run)
            if directory is not None:
                asset = run_file(directory, filename)
                if asset:
                    return asset, RUN_FILES[filename]
        return None
