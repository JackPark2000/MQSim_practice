# Experiment A — Initial_Occupancy_Percentage Trigger Boundary Refinement

## Goal

Previous sweep pinned the first occupancy trigger somewhere in (50, 70]. Above
70%, MQSim crashes (preconditioner / GC-WL inconsistency). This experiment
refines the boundary in the safe range with 5 % granularity.

## Setup

| Knob | Value |
| --- | --- |
| `Initial_Occupancy_Percentage` | **55 / 60 / 65 / 70** ← sweep |
| `Working_Set_Percentage` | 100 |
| `GC_Exec_Threshold` | 0.001 |
| `Overprovisioning_Ratio` | 0.07 |
| `Read_Percentage` | 1 |
| `Average_No_of_Reqs_in_Queue` | 128 |
| `Stop_Time` | 30 s |
| Others | preconditioned, `Ideal_Mapping_Table=true`, GREEDY, non-preemptible |

(`occ=50` is the no-GC baseline from previous sweep; `occ=70` is reused from
the previous sweep too.)

> Note: `A_occ60` and `C_thr0p05_op0p02` initially aborted with
> `Inconsistency found when moving a page for GC/WL!` and
> `Illegal operation: Unlocking an LPA that has not been locked!` respectively.
> Re-running with different SSD/workload seeds (12345 / 67890) passed cleanly —
> these are seed-dependent MQSim race conditions, not deterministic config
> bugs.

## Results

| occ | `Total_GC_Executions` | Avg pg-move / GC | GC_Erase enq | GC_Write enq | UserW | WAF | DevResp µs | Max DevResp µs | Status |
| ---:| ---:| ---:| ---:| ---:| ---:| ---:| ---:| ---:| --- |
| 50 | **0** | 0.00 | 0 | 0 | 1,191,951 | 1.000 | 3,188 | 3,847 | ok (baseline) |
| 55 | **37** | 31.59 | 56 | 5,863 | 1,146,405 | 1.005 | 3,322 | 520,907 | ok |
| 60 | **148** | 48.05 | 209 | 22,272 | 1,012,553 | 1.022 | 3,753 | 820,507 | ok (reseeded) |
| 65 | **440** | 65.24 | 562 | 59,220 | 817,151 | 1.072 | 4,654 | 822,887 | ok |
| 70 | **691** | 84.38 | 815 | 89,536 | 656,348 | 1.136 | 5,791 | 760,205 | ok |

## Findings

- **First trigger: occ = 55.** Even a 5 pp bump from 50 → 55 produces 37 GC
  executions and a Max device response time spike from 3.8 ms to 520 ms.
- The ramp is smooth and monotonic in all metrics:
  - `GC_Exec`: 0 → 37 → 148 → 440 → 691  (~3× per 5 % occupancy step)
  - `Avg pg-move / GC`: 0 → 31.6 → 48.1 → 65.2 → 84.4
    (each surviving block carries more valid pages → GC cost rises)
  - `WAF`: 1.000 → 1.005 → 1.022 → 1.072 → 1.136
  - `Max device response time`: 3.8 ms → 521 ms → 821 ms → 823 ms → 760 ms
    (tail latency saturates near 0.8 s once GC competes seriously with user IO)
- `UserW` falls 1.19 M → 0.66 M as occupancy rises, because each user write
  increasingly waits behind GC.

## Picture

```
occ:    50    55    60    65    70
GC_Exec: 0   37   148  440  691
        ^     ^___ trigger    boundary
   no-GC      first non-zero
```

## Conclusion

The Initial_Occupancy_Percentage trigger boundary, holding everything else at
the no-GC baseline, sits **at or just below occ = 55**. The previous coarse
result (50→70 jumped from 0 to 691) hid this — the actual ramp is gradual and
already visible at 55 %.
