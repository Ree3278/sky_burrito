# RL Fulfillment Rate Report

**Validated On:** April 19, 2026  
**Project:** `sky_burrito`  
**Fleet Sizes Tested:** `20 drones`, `30 drones`  
**Latest Retrained Checkpoints:** `models_retrained/fleet_20/ppo_fleet_20_phase_3.zip`, `models_retrained/fleet_30/ppo_fleet_30_phase_3.zip`  
**Long-Run Continuation Checkpoint:** `models_retrained_longrun/fleet_30/ppo_fleet_30_phase_3.zip`  
**Low-LR Fine-Tune Checkpoint:** `models_retrained_finetune_lr5e5/fleet_30/ppo_fleet_30_phase_3.zip`

---

## Executive Verdict

The RL result is only partially okay, and fleet size matters a lot.

- Phase 1 is strong: `100.0%` average fulfillment over 2 evaluation episodes.
- Phase 2 is strong: `99.9%` average fulfillment over 2 evaluation episodes.
- Phase 3 with `20` drones is still not strong enough after retraining: `62.9%` average fulfillment over 20 evaluation episodes.
- Phase 3 with `30` drones is much better after retraining: `86.0%` average fulfillment over 20 evaluation episodes.
- A longer continued Phase 3 run for `30` drones got worse, not better: `78.2%` average fulfillment over 20 evaluation episodes.
- A careful low-learning-rate fine-tune preserved the `30`-drone baseline, but did not materially improve it: `86.0%` average fulfillment over 20 evaluation episodes.

That means the saved single-hub and two-hub checkpoints look healthy, the full-network setup with `20` drones is still not ready, the full-network setup with `30` drones is materially better and is still the best baseline, and neither blindly training longer nor carefully fine-tuning at a lower learning rate solved the core backlog problem.

---

## What Was Tested

### Code-path validation

- `./.venv/bin/python -m compileall simulation test_multi_hub_env.py test_rl_multi_hub_steps.py test_rl_environment_regressions.py`
- `./.venv/bin/python test_rl_environment_regressions.py`
- `./.venv/bin/python test_multi_hub_env.py`
- `./.venv/bin/python test_rl_multi_hub_steps.py`
- `./.venv/bin/python simulation/rl_training.py --test-only`

### Saved-checkpoint evaluation

- `./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 1 --num-episodes 2`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 2 --num-episodes 2`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 3 --num-episodes 3`

### Phase 3 retraining and comparison

- `./.venv/bin/python -u simulation/rl_training.py --phase 3 --fleet-sizes 20 --no-gpu --checkpoint-dir models_retrained`
- `./.venv/bin/python -u simulation/rl_training.py --phase 3 --fleet-sizes 30 --no-gpu --checkpoint-dir models_retrained`
- `./.venv/bin/python -u simulation/rl_training.py --phase 3 --fleet-sizes 30 --no-gpu --timesteps 500000 --resume-from models_retrained/fleet_30/ppo_fleet_30_phase_3.zip --checkpoint-dir models_retrained_longrun`
- `./.venv/bin/python -u simulation/rl_training.py --phase 3 --fleet-sizes 30 --no-gpu --timesteps 100000 --learning-rate 5e-5 --resume-from models_retrained/fleet_30/ppo_fleet_30_phase_3.zip --checkpoint-dir models_retrained_finetune_lr5e5`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 3 --num-episodes 5 --checkpoint-dir models_retrained`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 3 --num-episodes 5`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained_longrun`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained --reward-breakdown`
- `./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained_finetune_lr5e5 --reward-breakdown`

---

## Measured Results

| Model | Scenario | Episodes | Reward | Average Fulfillment | Notes |
|---|---|---:|---:|---:|---|
| Phase 1 checkpoint | Single hub (`Hub 6`) | 2 | `98.30` | `100.0%` | Healthy under corrected timing |
| Phase 2 checkpoint | Two hubs (`Hub 11 <-> Hub 9`) | 2 | `648.87` | `99.9%` | Healthy under corrected timing |
| Original Phase 3 checkpoint | Full network (9 hubs) | 5 | `-269911.41` | `62.9%` | Corrected evaluation of original model |
| Retrained Phase 3 checkpoint | Full network (9 hubs, `20` drones) | 5 | `-266876.34` | `63.0%` | Slightly better reward, no material fulfillment gain |
| Retrained Phase 3 checkpoint | Full network (9 hubs, `20` drones) | 20 | `-270828.69` | `62.9%` | Longer evaluation confirms the same weak result |
| Retrained Phase 3 checkpoint | Full network (9 hubs, `30` drones) | 20 | `-127549.29` | `86.0%` | Current best full-network checkpoint |
| Continued Phase 3 checkpoint | Full network (9 hubs, `30` drones, longer run) | 20 | `-182339.55` | `78.2%` | Extra continuation with the same recipe degraded performance |
| Low-LR fine-tuned Phase 3 checkpoint | Full network (9 hubs, `30` drones) | 20 | `-127683.83` | `86.0%` | Preserved the baseline, but did not materially improve it |

### Retrained Phase 3 episode breakdown (`20` drones, 5-episode sample)

| Episode | Reward | Fulfillment |
|---|---:|---:|
| 1 | `-277387.03` | `62.4%` |
| 2 | `-266468.38` | `62.9%` |
| 3 | `-265237.66` | `63.2%` |
| 4 | `-258772.86` | `63.6%` |
| 5 | `-266515.94` | `63.1%` |

### Phase 3 comparison: `20` drones before and after retraining

| Checkpoint | Episodes | Avg Reward | Avg Fulfillment |
|---|---:|---:|---:|
| Original `models/fleet_20/...phase_3.zip` | 5 | `-269911.41` | `62.9%` |
| Retrained `models_retrained/fleet_20/...phase_3.zip` | 5 | `-266876.34` | `63.0%` |

Interpretation:
- retraining completed successfully
- reward improved a little
- fulfillment improved by only `0.1` percentage points
- the model is still far below a production-ready target

### Phase 3 comparison: retrained `20` drones vs retrained `30` drones

| Checkpoint | Episodes | Avg Reward | Avg Fulfillment |
|---|---:|---:|---:|
| Retrained `models_retrained/fleet_20/...phase_3.zip` | 20 | `-270828.69` | `62.9%` |
| Retrained `models_retrained/fleet_30/...phase_3.zip` | 20 | `-127549.29` | `86.0%` |

Interpretation:
- increasing from `20` to `30` drones improved fulfillment by `23.1` percentage points
- the 20-episode evaluation variance was small: about `0.5%` std dev for `20` drones and `0.6%` for `30` drones
- the improvement is much larger than anything gained by retraining the `20`-drone model longer with the same recipe
- fleet size is now the clearest lever for better Phase 3 performance in the corrected simulator

### Phase 3 comparison: best `30`-drone checkpoint vs longer continued `30`-drone checkpoint

| Checkpoint | Episodes | Avg Reward | Avg Fulfillment |
|---|---:|---:|---:|
| Retrained `models_retrained/fleet_30/...phase_3.zip` | 20 | `-127549.29` | `86.0%` |
| Continued `models_retrained_longrun/fleet_30/...phase_3.zip` | 20 | `-182339.55` | `78.2%` |

Interpretation:
- adding another `500,000` timesteps to the `30`-drone checkpoint hurt performance by `7.8` percentage points
- the current best full-network model is still `models_retrained/fleet_30/ppo_fleet_30_phase_3.zip`
- more training with the same optimizer settings is not automatically better, and can over-train or destabilize the policy

### Phase 3 comparison: best `30`-drone checkpoint vs low-LR fine-tuned `30`-drone checkpoint

| Checkpoint | Episodes | Avg Reward | Avg Fulfillment |
|---|---:|---:|---:|
| Retrained `models_retrained/fleet_30/...phase_3.zip` | 20 | `-127549.29` | `86.0%` |
| Low-LR fine-tuned `models_retrained_finetune_lr5e5/fleet_30/...phase_3.zip` | 20 | `-127683.83` | `86.0%` |

Interpretation:
- lowering the learning rate prevented the destructive collapse seen in the longer same-recipe continuation run
- however, it did not materially improve reward or fulfillment
- the fine-tune is effectively a stable tie with the current best checkpoint, not a new winner

### Why is the reward still so low?

The reward is low mainly because the queue-backlog penalty dominates everything else.

For the current best `30`-drone checkpoint over `20` evaluation episodes:

| Reward component | Average contribution per episode |
|---|---:|
| Fulfillment bonus | `+5062.68` |
| Queue penalty | `-132637.12` |
| Craning penalty | `0.00` |
| Deadhead penalty | `0.00` |
| Idle bonus | `+25.16` |
| Total reward | `-127549.29` |

Supporting averages per step:

| Step-level driver | Average |
|---|---:|
| Queue length | `921.1` orders |
| Orders fulfilled per step | `7.0` |
| Deadheading drones per step | `0.0` |
| Idle drones | `8.9` |

Interpretation:
- the queue term is by far the dominant reward term
- even with `86.0%` fulfillment, the model still carries a very large backlog through the day
- the agent is not losing reward to craning
- the agent is not losing reward to deadheading either, which suggests rebalancing is not being used aggressively enough to reduce backlog
- this is why reward stays strongly negative even when fulfillment looks fairly good

### Reward breakdown after low-LR fine-tuning

The low-LR fine-tuned checkpoint shows almost the same reward anatomy:

| Reward component | Average contribution per episode |
|---|---:|
| Fulfillment bonus | `+5049.23` |
| Queue penalty | `-132758.51` |
| Craning penalty | `0.00` |
| Deadhead penalty | `0.00` |
| Idle bonus | `+25.45` |
| Total reward | `-127683.83` |

This is strong evidence that the optimizer was no longer the main bottleneck. The reward is low because the policy still leaves too much order backlog in the system.

### Does running more episodes help?

Yes for evaluation confidence, no for model quality by itself.

- More evaluation episodes help because they reduce noise and show whether a result is stable.
- That is why the `20 vs 30` comparison above uses `20` episodes each instead of only `5`.
- More training timesteps can sometimes help a model improve, but the earlier retrained `20`-drone run already showed that simply rerunning the same Phase 3 recipe was not enough.
- The longer continued `30`-drone run showed the other failure mode too: more training can also make a previously good checkpoint worse.
- The low-LR fine-tune showed the more careful version of that experiment: it preserved the baseline, but still did not fix the backlog-driven reward problem.
- In this project, changing the fleet size from `20` to `30` helped far more than just adding another similar `20`-drone training run.

---

## Bugs Found And Fixed

### 1. Episode timing was wrong

Before the fix, the environment comments/config assumed one-minute steps, but the implementation effectively advanced the clock in one-second steps when `sim_speedup=60`.

Impact:
- episodes were much longer than intended
- reported step counts and training assumptions did not match

Fix:
- `simulation/rl_fleet_env.py` now uses `step_minutes = 60 / sim_speedup`
- a 24-hour run with `sim_speedup=60` now produces `1440` steps as intended

### 2. Phase curriculum hubs were not actually enforced

Before the fix, Phase 1 and Phase 2 still used the full 9-hub environment even though the curriculum config said otherwise.

Impact:
- “single hub” and “two hub” training/evaluation were not truly phase-specific

Fix:
- `simulation/rl_fleet_env.py` now accepts `active_hubs`
- `simulation/rl_training.py` passes curriculum hub subsets into the environment
- `simulation/rl_inference.py` now evaluates checkpoints with the matching phase setup

### 3. Drones could serve orders unrealistically

Before the fix, fulfilled orders did not actually keep drones busy for a service duration, and some per-step counters were effectively cumulative artifacts.

Impact:
- fulfillment and utilization were too optimistic
- reward signals were less trustworthy than they looked

Fix:
- drones now enter a busy delivery state for a service duration
- idle capacity drops while deliveries are in progress
- per-step fulfillment and deadheading counters reset each step
- aggregate fleet metrics are synchronized from actual drone state

### 4. Training output overstated percentages

Before the fix, training printed fulfillment with `:.1%` even though the environment already returned a `0-100` percentage.

Impact:
- values like `100.0` were displayed as `10,000.0%`
- some older markdown reports inherited that formatting error

Fix:
- `simulation/rl_training.py` now prints fulfillment with `:.1f}%`
- `simulation/rl_inference.py` now prints cleaner percentage columns

### 5. RL dependencies were missing from the package manifest

Before the fix, `pyproject.toml` did not list the RL packages required by the training and inference scripts.

Fix:
- added `gymnasium`
- added `stable-baselines3`
- added `tensorboard`
- added `torch`

---

## New Regression Coverage

`test_rl_environment_regressions.py` now checks:

- phase-specific hub activation
- one-minute step timing for `sim_speedup=60`
- delivery capacity is consumed while drones are busy
- per-step fulfillment counters reset correctly
- rebalancing stays inside the active hub subset

---

## Training Utility Update

`simulation/rl_training.py` now supports:

- `--resume-from` to continue training from an existing checkpoint
- `--timesteps` to override the default training duration for controlled comparisons
- `--learning-rate` to run lower-risk fine-tuning experiments from a saved checkpoint

`simulation/rl_inference.py` now supports:

- `--reward-breakdown` to print average reward-component contributions and step-level drivers during evaluation

This was added so longer-run experiments can be tested without overwriting the current best checkpoint.

---

## Final Assessment

### What is okay right now

- the RL code path runs
- the environment smoke tests pass
- Phase 1 and Phase 2 checkpoints perform very well under the corrected simulator

### What is not okay yet

- the original and retrained Phase 3 checkpoints for `20` drones are both only around `63%` fulfillment
- older markdown files may still contain pre-fix or over-reported claims

### What is promising now

- the retrained Phase 3 checkpoint for `30` drones reached `86.0%` fulfillment over `20` evaluation episodes
- this is a real improvement under the corrected simulator, not just a formatting artifact

### Recommended next action

Retraining alone did not close the gap for `20` drones, a naive longer continuation run on `30` drones made the model worse, and a low-LR fine-tune preserved but did not improve the baseline. The next meaningful step should directly target backlog reduction, for example:

- keep `30` drones as the baseline for full-network experiments
- change the Phase 3 reward so backlog reduction is shaped more directly instead of letting raw queue length dominate the entire score
- improve the dispatch/rebalancing logic, because the current best policy is effectively using `0.0` deadheads per step on average
- reduce demand intensity or rebalance the reward if Phase 3 is still over-penalized by backlog

If you want to rerun the matched comparison:

```bash
./.venv/bin/python simulation/rl_inference.py --fleet-size 20 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained
./.venv/bin/python simulation/rl_inference.py --fleet-size 30 --phase 3 --num-episodes 20 --checkpoint-dir models_retrained
```

The honest status after retraining is:

`Phase 1 good` | `Phase 2 good` | `Phase 3: 20 weak, 30 best at 86.0%, longer continuation worse, low-LR fine-tune flat`
