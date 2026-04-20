# RL Documentation Index

**Last Updated:** April 19, 2026  
**Current Validation Status:** `Phase 1 OK` | `Phase 2 OK` | `Phase 3: 20 weak, 30 best, longer continuation worse, low-LR fine-tune flat`

---

## Start Here

If you want the current truth instead of older optimistic notes, read these first:

1. `FULFILLMENT_RATE_REPORT.md`
   Current validation summary, measured fulfillment, and the code changes made on April 18-19, 2026.
2. `test_rl_environment_regressions.py`
   Regression checks for timing, phase-specific hub activation, and delivery-capacity accounting.
3. `simulation/rl_inference.py`
   The command-line evaluation entry point for saved checkpoints.
4. `simulation/rl_training.py`
   The curriculum/training entry point.
5. `simulation/rl_fleet_env.py`
   The corrected RL environment.

---

## What To Trust Right Now

### Verified on April 18-19, 2026

- `FULFILLMENT_RATE_REPORT.md`
- `test_rl_environment_regressions.py`
- `test_multi_hub_env.py`
- `test_rl_multi_hub_steps.py`
- `simulation/rl_fleet_env.py`
- `simulation/rl_training.py`
- `simulation/rl_inference.py`

### Historical / Read With Caution

These files may still be useful for context, but some of them were written before the latest validation fixes:

- `RL_TRAINING_MULTI_HUB_COMPLETE.md`
- `RL_TRAINING_CONVERGENCE_VALIDATION.md`
- `RL_FULFILLMENT_FIX_COMPLETE.md`
- `PHASE_1_TRAINING_COMPLETE.md`
- `PHASE_2_TRAINING_COMPLETE.md`
- `PHASE_3_READY.md`
- `00_RL_COMPLETE_STATUS.md`

Reason:
- older docs mixed together pre-fix and post-fix assumptions
- phase 1/2 were previously reported with a percentage-formatting bug
- phase timing previously ran at one-second steps instead of one-minute steps
- curriculum hub subsets were previously not enforced by the environment

---

## Current Measured Results

These are the latest checkpoint evaluations after correcting the environment and inference path:

| Phase | Scenario | Episodes | Average Fulfillment | Verdict |
|---|---|---:|---:|---|
| 1 | Single hub (`Hub 6`) | 2 | `100.0%` | Good |
| 2 | Two hubs (`Hub 11 <-> Hub 9`) | 2 | `99.9%` | Good |
| 3 | Full network (9 hubs, retrained `20`-drone checkpoint) | 20 | `62.9%` | Not ready |
| 3 | Full network (9 hubs, retrained `30`-drone checkpoint) | 20 | `86.0%` | Current best baseline |
| 3 | Full network (9 hubs, longer continued `30`-drone checkpoint) | 20 | `78.2%` | Worse than the baseline |
| 3 | Full network (9 hubs, low-LR fine-tuned `30`-drone checkpoint) | 20 | `86.0%` | Stable tie, not a new winner |

Interpretation:
- Phase 1 and Phase 2 behave well under the corrected simulator.
- Phase 3 with `20` drones is materially weaker than the simpler phases and should not be treated as deployment-ready.
- Phase 3 with `30` drones is much stronger and is the better baseline for any next tuning pass.
- A naive longer continuation run for the `30`-drone checkpoint made the model worse, so more training is not automatically better.
- A low-LR fine-tune avoided that collapse, but it did not materially improve reward or fulfillment.
- Reward diagnostics show the queue-backlog penalty is the dominant negative term by far.
- More evaluation episodes helped confirm stability, but the real gain came from the fleet-size change.

---

## Quick Commands

### Run validation

```bash
./.venv/bin/python test_rl_environment_regressions.py
./.venv/bin/python test_multi_hub_env.py
./.venv/bin/python test_rl_multi_hub_steps.py
```

### Evaluate saved models

```bash
./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 1 --num-episodes 2
./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 2 --num-episodes 2
./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained
./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained
./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained_longrun
./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained_finetune_lr5e5 --reward-breakdown
```

### Smoke-test the training entry point

```bash
./.venv/bin/python simulation/rl_training.py --test-only
```

### Continue training from a saved checkpoint

```bash
./.venv/bin/python simulation/rl_training.py --phase 3 --fleet-sizes 30 --no-gpu --timesteps 500000 --resume-from models_retrained/fleet_30/ppo_fleet_30_phase_3.zip --checkpoint-dir models_retrained_longrun
./.venv/bin/python simulation/rl_training.py --phase 3 --fleet-sizes 30 --no-gpu --timesteps 100000 --learning-rate 5e-5 --resume-from models_retrained/fleet_30/ppo_fleet_30_phase_3.zip --checkpoint-dir models_retrained_finetune_lr5e5
```

---

## Code Areas

### Environment

- `simulation/rl_fleet_env.py`
  Phase-aware hub activation, corrected step timing, busy-drone tracking, and synchronized fleet metrics.

### Training

- `simulation/rl_training.py`
  Uses curriculum hub subsets when building the environment, prints fulfillment percentages correctly, and now supports `--resume-from`, `--timesteps`, and `--learning-rate` for continuation and fine-tuning experiments.

### Inference

- `simulation/rl_inference.py`
  Evaluates checkpoints against the matching phase configuration, prints readable fulfillment summaries, and can now show reward-component breakdowns.

### Packaging

- `pyproject.toml`
  Now declares the RL runtime dependencies that the training/inference code actually needs.

---

## Recommended Next Step

If the goal is a trustworthy full-network RL policy, the next step is:

1. Use the `30`-drone Phase 3 checkpoint as the current baseline instead of the `20`-drone one.
2. Tune the Phase 3 setup instead of simply rerunning the same recipe for more timesteps.
3. Prioritize backlog-focused reward shaping or better rebalancing logic, because diagnostics show queue penalty is the main reason total reward stays low.
4. Re-run `simulation/rl_inference.py` for at least `10-20` episodes against the next checkpoint.
5. Update `FULFILLMENT_RATE_REPORT.md` with the new comparison numbers.
