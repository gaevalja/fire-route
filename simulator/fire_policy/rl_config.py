"""Adjustable evacuation and training settings.

The fire scenario's physical parameters remain in ``config.js`` and are mirrored
by ``rl_sim.py``.  A training run records copies of these files for provenance.
"""

from dataclasses import asdict, dataclass
import hashlib


DEATH_REWARD_SCHEME = "discount_neutral_death_v2"


@dataclass(frozen=True)
class EvacuationRules:
    train_wind: int = 10
    eval_winds: tuple[int, ...] = (1, 5, 10, 15)
    training_scenario_seed_max: int = 1_000_000_000
    awareness_seconds: int = 180
    action_seconds: int = 30
    slow_move_fire_above: float = 40.0
    slow_move_smoke_above: float = 65.0
    slow_move_seconds: int = 60
    fire_death_at: float = 60.0
    smoke_death_at: float = 80.0
    roof_rescue_at: int = 21 * 60
    room_rescue_at: int = 23 * 60
    room_rescue_fire_max: float = 50.0
    exit_reward: float = 10.0
    roof_reward: float = 10.0
    room_reward: float = 10.0
    death_reward: float = -200.0
    elevator_death_reward: float = -400.0
    time_cost_per_second: float = 0.0005
    fire_cost_per_second: float = 0.002
    smoke_cost_per_second: float = 0.001
    fire_high_risk_start: float = 20.0
    smoke_high_risk_start: float = 40.0
    fire_high_risk_cost_per_second: float = 0.06
    smoke_high_risk_cost_per_second: float = 0.03
    time_observation_scale: int = 25 * 60

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TrainingSettings:
    total_timesteps: int = 800_000
    parallel_envs: int = 8
    scenario_revisit_probability: float = 0.10
    scenario_pool_candidates: int = 5_000
    room_pool_candidates: int = 2_000
    room_pool_min_floor: int = 6
    scenario_pool_seed: int = 20_271_117
    initial_first_floor_ignition_probability: float = 0.0
    initial_second_floor_ignition_probability: float = 0.0
    ignition_curriculum_hold_fraction: float = 0.35
    ignition_curriculum_end_fraction: float = 0.80
    rollout_steps_per_env: int = 1024
    minibatch_size: int = 256
    update_epochs: int = 10
    learning_rate: float = 0.0003
    gamma: float = 1.0
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    value_loss_coefficient: float = 0.5
    entropy_coefficient: float = 0.01
    hidden_layers: tuple[int, int] = (128, 128)
    seed: int = 2026
    eval_episodes_per_wind: int = 200

    def as_dict(self) -> dict:
        return asdict(self)

    def ignition_probabilities(self, progress: float) -> tuple[float, float]:
        """Training-only forced ignition probabilities for a rollout progress value."""
        if not 0 <= progress <= 1:
            raise ValueError("Training progress must be in [0, 1]")
        if not 0 <= self.ignition_curriculum_hold_fraction < self.ignition_curriculum_end_fraction <= 1:
            raise ValueError("Ignition curriculum boundaries must satisfy 0 <= hold < end <= 1")
        probabilities = (self.initial_first_floor_ignition_probability,
                         self.initial_second_floor_ignition_probability)
        if any(not 0 <= probability <= 1 for probability in probabilities) or sum(probabilities) > 1:
            raise ValueError("Initial forced ignition probabilities must sum to at most 1")
        if progress <= self.ignition_curriculum_hold_fraction:
            scale = 1.0
        elif progress >= self.ignition_curriculum_end_fraction:
            scale = 0.0
        else:
            scale = ((self.ignition_curriculum_end_fraction - progress)
                     / (self.ignition_curriculum_end_fraction - self.ignition_curriculum_hold_fraction))
        return probabilities[0] * scale, probabilities[1] * scale


RULES = EvacuationRules()
TRAINING = TrainingSettings()


def evaluation_start_room(scenario_seed: int, room_ids) -> str:
    """Same start room for a scenario seed across runs and wind settings."""
    index = (int(scenario_seed) * 2_654_435_761 + 1_013_904_223) % len(room_ids)
    return room_ids[index]


def evaluation_scenario_seed(offset: int, seed_base: int = 2_000_000_000) -> int:
    """Disperse test fires across rooms and avoid the training seed range.

    Consecutive engine seeds produce nearby ignition draws, so a plain
    ``seed_base + offset`` is a biased evaluation sample.
    """
    if offset < 0:
        raise ValueError("Evaluation offset must be nonnegative")
    digest = hashlib.blake2b(f"{seed_base}:{offset}".encode("ascii"), digest_size=8).digest()
    return 1_000_000_001 + int.from_bytes(digest, "big") % (2**32 - 1_000_000_001)
