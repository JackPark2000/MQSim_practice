# Experiment 2 — Per-parameter follow-up sweeps

Three follow-up experiments designed from the previous 4×5 sweep, splitting
the parameter knobs by what they actually do in MQSim's GC model.

## Reports

| Sub-experiment | Goal | Report | Headline |
| --- | --- | --- | --- |
| **A** | refine the `Initial_Occupancy_Percentage` trigger boundary | [`EXP2_A.md`](EXP2_A.md) | first trigger at **occ = 55** |
| **B** | re-test working set under **GC-on** conditions (cost shaper, not trigger) | [`EXP2_B.md`](EXP2_B.md) | `AvgPgMv` falls **40.65 → 35.01** (ws 100 → 5) |
| **C** | 2D heatmap of `GC_Exec_Threshold` × `Overprovisioning_Ratio` | [`EXP2_C.md`](EXP2_C.md) | one no-GC corner, one saturated corner, `thr` dominates count, OP dominates per-GC cost |

## What was actually run

- **34 unique configs** total (4 + 5 + 25). 11 of those exactly match runs from
  the previous `sweep/` so their output XMLs are reused (symlinked into
  `exp2/runs/`). **23 new MQSim runs** done here, all at 6-way parallel.
- **2 reruns**: `A_occ60` and `C_thr=0.05, OP=0.02` initially aborted with
  seed-dependent MQSim race conditions
  (`Inconsistency found when moving a page for GC/WL!` /
  `Illegal operation: Unlocking an LPA that has not been locked!`).
  Re-running with different seeds (12345 / 67890) passed cleanly — full grid
  now intact.

## Heatmaps (rendered PNGs)

| Metric | File | What it shows |
| --- | --- | --- |
| `Total_GC_Executions` (log scale) | `heatmap_GC_Exec.png` | trigger frontier between thr cols 0.005 and 0.025; one true no-GC corner |
| `Write Amplification` | `heatmap_WAF.png` | WAF stays ≤ 1.07 except in the rightmost thr column (≥ 1.22) |
| `Avg_Page_Movement_For_GC` | `heatmap_AvgPgMv.png` | monotonic both axes; rises 0 → 49.6 from upper-left to lower-right corner |
| `Avg Device Response Time` | `heatmap_DevResp.png` | baseline 3.2 ms → 6.3 ms worst corner |
| `Max Device Response Time` (log) | `heatmap_MaxResp.png` | tail latency: <4 ms only in no-GC cell, 0.2-0.8 s everywhere else |

## Cross-cutting findings

1. **Occupancy boundary is at occ = 55**, not 70. The previous sweep's coarse
   step (50 → 70) hid the gradual onset of GC.
2. **Working set is decoupled from the trigger condition** but is the *clearest*
   knob for per-GC cost shaping: −14 % `AvgPgMv` from ws=100 to ws=5.
3. **Threshold and OP are duals but asymmetric in effect**:
   - `thr` is the dominant lever for **count** of GC.
   - `OP` is the dominant lever for **cost** of each GC.
   - The 2D grid makes this visible cell-by-cell.
4. The whole frontier sits **right around `thr ≈ 0.01`**, consistent with the
   post-preconditioning free pool of ~10-20 blocks/plane derived in the
   previous sweep report (`sweep/SWEEP.md`).

## Reproduction

```bash
cd ~/mqsim_gc_exp/MQSim
python3 exp2/aggregate.py           # re-parses, writes summaries.json + results.json
# Heatmaps:
python3 - << 'PY'
import json, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
# (see exp2/EXP2_C.md "Interpretation as a heatmap" section for the snippet)
PY
```

## Artifacts

```
exp2/
├── EXP2.md                  ← this index
├── EXP2_A.md  EXP2_B.md  EXP2_C.md
├── aggregate.py             ← parser, run after changes
├── aggregate.out            ← latest console table
├── manifest.json            ← 34 cell config map (NEW / REUSED markers)
├── to_run.json              ← 23 names re-run here
├── results.json             ← all per-cell parsed metrics
├── summaries.json           ← machine-readable A_rows / B_rows / C_grid
├── heatmap_*.png            ← 5 rendered heatmaps for experiment C
├── configs/, workloads/     ← per-cell ssd.xml / wl.xml inputs
├── runs/   <name>/          ← MQSim working dir + wl_scenario_1.xml output
└── logs/   <name>.log
```
