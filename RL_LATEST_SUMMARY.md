# RL Latest Summary

**Validated On:** April 19, 2026  
**Project:** `sky_burrito`

## What I Did

- Fixed the RL environment so training and evaluation match the intended simulation:
  - corrected step timing to `1 minute` per step
  - enforced phase-specific `active_hubs`
  - made drones stay busy while delivering
  - reset per-step counters correctly
  - synchronized aggregate fleet metrics from actual drone state
- Fixed RL reporting and packaging:
  - corrected percentage formatting in training and inference
  - added missing RL dependencies in `pyproject.toml`
- Added regression coverage in `test_rl_environment_regressions.py`
- Added training continuation support in `simulation/rl_training.py`:
  - `--resume-from`
  - `--timesteps`
  - `--learning-rate`
- Added reward diagnostics in `simulation/rl_inference.py` so evaluation now shows why total reward is low

## Main Files Changed

- `simulation/rl_fleet_env.py`
- `simulation/rl_training.py`
- `simulation/rl_inference.py`
- `pyproject.toml`
- `test_rl_environment_regressions.py`

## What I Tested

- `./.venv/bin/python -m compileall simulation test_multi_hub_env.py test_rl_multi_hub_steps.py test_rl_environment_regressions.py`
- `./.venv/bin/python test_rl_environment_regressions.py`
- `./.venv/bin/python test_multi_hub_env.py`
- `./.venv/bin/python test_rl_multi_hub_steps.py`
- `./.venv/bin/python simulation/rl_training.py --test-only`
- saved-checkpoint evaluation for Phase 1, Phase 2, and Phase 3
- corrected retraining for Phase 3 with `20` drones
- corrected retraining for Phase 3 with `30` drones
- longer continuation run for the best `30`-drone checkpoint
- low-learning-rate fine-tune for the best `30`-drone checkpoint

## Current Results

| Scenario | Episodes | Avg Reward | Avg Fulfillment | Verdict |
|---|---:|---:|---:|---|
| Phase 1, `20` drones | 2 | `98.30` | `100.0%` | Good |
| Phase 2, `20` drones | 2 | `648.87` | `99.9%` | Good |
| Phase 3, retrained `20` drones | 20 | `-270828.69` | `62.9%` | Not ready |
| Phase 3, retrained `30` drones | 20 | `-127549.29` | `86.0%` | Best current baseline |
| Phase 3, longer continuation on `30` drones | 20 | `-182339.55` | `78.2%` | Worse |
| Phase 3, low-LR fine-tune on `30` drones | 20 | `-127683.83` | `86.0%` | Stable tie |

## Best Current Checkpoint

- `models_retrained/fleet_30/ppo_fleet_30_phase_3.zip`

This is still the best full-network model.  
The longer same-recipe continuation got worse, and the lower-LR fine-tune stayed roughly flat.

## Why The Reward Is So Low

The reward is low mainly because the queue-backlog penalty dominates the score.

For the current best `30`-drone checkpoint over `20` episodes:

| Reward Component | Avg Contribution Per Episode |
|---|---:|
| Fulfillment bonus | `+5062.68` |
| Queue penalty | `-132637.12` |
| Craning penalty | `0.00` |
| Deadhead penalty | `0.00` |
| Idle bonus | `+25.16` |
| Total reward | `-127549.29` |

Supporting averages per step:

| Driver | Average |
|---|---:|
| Queue length | `921.1` orders |
| Orders fulfilled per step | `7.0` |
| Deadheading drones per step | `0.0` |
| Idle drones | `8.9` |

Interpretation:

- fulfillment is fairly good, but backlog is still very large
- reward is not being dragged down by craning
- reward is not being dragged down by deadheading either
- the policy is not using rebalancing aggressively enough to reduce queue pressure
- the main remaining problem is backlog, not basic simulator correctness

## What This Means

- The code path is now much more trustworthy than before.
- Phase 1 and Phase 2 are healthy.
- Phase 3 with `20` drones is still weak.
- Phase 3 with `30` drones is much better and should be the current baseline.
- More training alone is not enough.
- The next useful improvement should target backlog reduction directly:
  - reward shaping
  - better rebalancing logic
  - demand-pressure tuning if needed

## Docs Cleanup

This file replaces the older RL status/report markdown files that were conflicting with the corrected validation.

Deleted outdated RL markdown files:

- `00_RL_COMPLETE_STATUS.md`
- `PHASE_1_TRAINING_COMPLETE.md`
- `PHASE_2_TRAINING_COMPLETE.md`
- `PHASE_3_READY.md`
- `RL_TRAINING_MULTI_HUB_COMPLETE.md`
- `RL_TRAINING_CONVERGENCE_VALIDATION.md`
- `RL_FULFILLMENT_FIX_COMPLETE.md`
- `FULFILLMENT_RATE_REPORT.md`
- `RL_DOCUMENTATION_INDEX.md`
