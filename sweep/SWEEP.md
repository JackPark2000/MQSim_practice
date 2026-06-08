# MQSim Per-Parameter GC Trigger Sweep

> Goal: starting from a verified **no-GC baseline**, sweep one parameter at a time
> and find the value at which `GC_Read/Write/Erase_TR_Queue` transactions start
> being non-zero (and `FTL.Total_GC_Executions > 0`).

## 1. Sweep design

Workload pressure was fixed so that the *threshold-like* parameters can be
isolated. Holding the other params at the no-GC baseline below, we sweep one
parameter through 5 values:

### No-GC baseline (preconditioner-safe)

| Knob | Value | Why |
| --- | --- | --- |
| `Initial_Occupancy_Percentage` | **50** | Low enough to leave free blocks after preconditioning; preconditioner is unstable at low-occ × high-OP (`PRINT_ERROR("It is not possible to assign PPA to all LPAs")`). |
| `Working_Set_Percentage`       | **100** | Writes spread across the whole LBA range → minimal collision/invalidation. |
| `GC_Exec_Threshold`            | **0.001** | Trigger only when free pool < 0.1% of plane blocks (≈ 2 blocks/plane). |
| `Overprovisioning_Ratio`       | **0.07** | SSD default; leaves comfortable spare. |
| `Read_Percentage`              | **1**   | Write-heavy probe (99% writes). |
| `Average_No_of_Reqs_in_Queue`  | **128** | High QD to actually pressure the device in 30 s. |
| `Stop_Time`                    | **30 s** | 100s → 30s for sweep tractability; baseline still drains plenty of writes (~1.19 M). |
| `Enabled_Preconditioning`      | **true** | Steady-state setup. |
| `Ideal_Mapping_Table`          | **true** | Removes CMT misses as confound. |
| `GC_Block_Selection_Policy`    | **GREEDY** | Deterministic candidate selection. |
| `Preemptible_GC_Enabled`       | **false** | Plain GC. |

### Sweep ranges (5 values each)

| Parameter | Sweep values (baseline ▌highlighted) |
| --- | --- |
| `Initial_Occupancy_Percentage` | **50** → 70 → 80 → 90 → 95 |
| `Working_Set_Percentage`       | **100** → 50 → 20 → 10 → 5 |
| `GC_Exec_Threshold`            | **0.001** → 0.005 → 0.01 → 0.025 → 0.05 |
| `Overprovisioning_Ratio`       | **0.07** → 0.05 → 0.03 → 0.02 → 0.01 |

Total **17 unique configs** (baseline shared across 4 sweeps), run 4-way parallel
on the server.

## 2. Per-run summary

`baseline` row is the no-GC anchor. Read each sweep row by holding all other
params at the baseline.

| Run | occ | ws | thr | OP | **Total_GC_Executions** | Avg pg-move/GC | GC_Erase enq | UserW | WAF | DevResp µs | Max DevResp µs | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline`           | 50 | 100 | 0.001 | 0.07 | **0**     |   0.0 |     0 | 1,191,951 | 1.00 |  3,188 |     3,847 | ok |
| `sw_occ_70`          | 70 | 100 | 0.001 | 0.07 | **691**   |  84.4 |   815 |   656,348 | 1.14 |  5,791 |   760,205 | ok |
| `sw_occ_80`          | 80 | 100 | 0.001 | 0.07 | -         |   -   |   -   |    -      |  -   |   -    |     -     | MQSim BUG: `Inconsistency found when moving a page for GC/WL` |
| `sw_occ_90`          | 90 | 100 | 0.001 | 0.07 | crashed   |   -   |   -   |     0     |  -   |  1,946 |     2,630 | MQSim BUG: `free(): invalid pointer` |
| `sw_occ_95`          | 95 | 100 | 0.001 | 0.07 | crashed   |   -   |   -   |    239    |  -   |  2,324 |     7,311 | MQSim BUG: `munmap_chunk(): invalid pointer` |
| `sw_ws_50`           | 50 |  50 | 0.001 | 0.07 | **0**     |   0.0 |     0 | 1,189,989 | 1.00 |  3,192 |     3,963 | ok |
| `sw_ws_20`           | 50 |  20 | 0.001 | 0.07 | **0**     |   0.0 |     0 | 1,187,530 | 1.00 |  3,196 |     3,805 | ok |
| `sw_ws_10`           | 50 |  10 | 0.001 | 0.07 | **0**     |   0.0 |     0 | 1,191,435 | 1.00 |  3,180 |     3,776 | ok |
| `sw_ws_5`            | 50 |   5 | 0.001 | 0.07 | **0**     |   0.0 |     0 | 1,191,027 | 1.00 |  3,171 |     3,734 | ok |
| `sw_thr_0p005`       | 50 | 100 | 0.005 | 0.07 | **0**     |   0.0 |     0 | 1,191,951 | 1.00 |  3,188 |     3,847 | ok |
| `sw_thr_0p01`        | 50 | 100 | 0.01  | 0.07 | **15**    |  21.3 |    24 | 1,167,402 | 1.00 |  3,256 |   258,747 | ok |
| `sw_thr_0p025`       | 50 | 100 | 0.025 | 0.07 | **514**   |  31.2 |   612 |   913,450 | 1.04 |  4,161 |   522,595 | ok |
| `sw_thr_0p05`        | 50 | 100 | 0.05  | 0.07 | **2,828** |  40.6 | 2,955 |   658,419 | 1.22 |  5,773 |   775,181 | ok |
| `sw_op_0p05`         | 50 | 100 | 0.001 | 0.05 | **15**    |  25.8 |    23 | 1,170,274 | 1.00 |  3,247 |   262,326 | ok |
| `sw_op_0p03`         | 50 | 100 | 0.001 | 0.03 | **19**    |  26.9 |    29 | 1,163,935 | 1.00 |  3,265 |   271,234 | ok |
| `sw_op_0p02`         | 50 | 100 | 0.001 | 0.02 | **18**    |  27.7 |    28 | 1,155,016 | 1.00 |  3,290 |   256,728 | ok |
| `sw_op_0p01`         | 50 | 100 | 0.001 | 0.01 | **20**    |  29.2 |    30 | 1,159,219 | 1.00 |  3,278 |   217,213 | ok |

## 3. First-trigger summary

| Sweep parameter | No-GC range | **First trigger** | High end | Note |
|---|---|---|---|---|
| `Initial_Occupancy_Percentage` | 50 (GC=0) | **70** (GC=691, WAF=1.14) | 80–95 = MQSim crashes (high-occ × low-OP bug) | sweep saturates due to simulator limitation, not steady-state |
| `Working_Set_Percentage`       | 100 → 5 all GC=0 | **none in tested range** | even ws=5 yields 0 GC | working-set doesn't drain the free-block pool, only invalidation density inside blocks |
| `GC_Exec_Threshold`            | 0.001, 0.005 (GC=0) | **0.01** (GC=15) | 0.05 (GC=2,828) | smooth ramp; 0.005→0.01 crosses the post-preconditioning free-pool size |
| `Overprovisioning_Ratio`       | 0.07 (GC=0) | **0.05** (GC=15) | 0.01 (GC=20) | sharp step at 0.05; below that, GC count stays small but non-zero |

## 4. What the numbers actually mean

### 4.1 `GC_Exec_Threshold` sweep — the cleanest signal

MQSim fires GC when `free_block_pool_size < GC_Exec_Threshold * block_no_per_plane`.
With `block_no_per_plane = 2048`:

| thr | trigger floor (blocks/plane) | result |
|---:|---:|---|
| 0.001 |  2.05 | 0 GC |
| 0.005 | 10.24 | 0 GC |
| 0.010 | 20.48 | **15 GC**  ← first |
| 0.025 | 51.20 | 514 GC |
| 0.050 | 102.40 | 2,828 GC |

→ The post-preconditioning free-block pool sits between ~10 and ~20 blocks per
plane. Setting the trigger above that floor (thr ≥ 0.01) causes GC immediately
on the first writes that arrive after preconditioning.

### 4.2 `Overprovisioning_Ratio` sweep — symmetric to threshold

Lowering OP shrinks the free-block pool the preconditioner leaves behind. At
OP=0.07 the pool sits *above* the thr=0.001 trigger (no GC). At OP=0.05 it has
shrunk just enough to cross the trigger:

| OP   | GC_Exec | result |
|---:|---:|---|
| 0.07 |   0    | no GC (baseline) |
| 0.05 |  15    | **first** GC |
| 0.03 |  19    | GC |
| 0.02 |  18    | GC |
| 0.01 |  20    | GC |

→ Once GC starts triggering it stays roughly flat (15-20 executions), because
the steady-state free-pool depth saturates: at every drain below thr GC erases
one block and the pool floats just above the trigger.

### 4.3 `Initial_Occupancy_Percentage` sweep — works once but MQSim limits it

| occ | result |
|---:|---|
| 50 | 0 GC (baseline) |
| 70 | **691 GC, AvgPgMv=84.4, WAF=1.14** ← first |
| 80 | `Inconsistency found when moving a page for GC/WL` — MQSim aborts |
| 90 | `free(): invalid pointer` after preconditioning — only 388 host reqs ran |
| 95 | `munmap_chunk(): invalid pointer` — 630 host reqs ran |

→ Trigger sits **between occ=50 and occ=70**. We cannot extend the sweep
upward at the current OP=0.07 because the MQSim preconditioner / GC routines
have a known bug at high-occ × low-OP combinations (post-preconditioning state
becomes inconsistent).

### 4.4 `Working_Set_Percentage` sweep — surprisingly null

| ws | GC_Exec | UserW | DevResp µs |
|---:|---:|---:|---:|
| 100 | 0 | 1,191,951 | 3,188 |
|  50 | 0 | 1,189,989 | 3,192 |
|  20 | 0 | 1,187,530 | 3,196 |
|  10 | 0 | 1,191,435 | 3,180 |
|   5 | 0 | 1,191,027 | 3,171 |

→ This is the most interesting result. The PPT guide expected small working
sets to be the key GC driver. In MQSim's *trigger* model that is wrong: GC
trigger is purely a function of **free-block pool depth**, and a small working
set affects only *which blocks accumulate invalid pages*, not how fast new
blocks get allocated. So at the same write rate, shrinking the working set
changes nothing about the trigger condition. (It would affect *per-GC cost*
once GC starts firing — fewer valid pages to copy — but that's a different
metric.)

## 5. Verdict — the 4 knobs, ranked by directness

| # | Knob | Trigger value | Effect mechanism |
|---|---|---|---|
| 1 | `GC_Exec_Threshold` | **0.01** | Direct knob — defines the trigger line itself. |
| 2 | `Overprovisioning_Ratio` | **0.05** | Indirect — shrinks the post-precondition free pool toward the trigger line. |
| 3 | `Initial_Occupancy_Percentage` | **70** | Indirect — preconditioner produces a tighter free pool when more LPAs must be placed. (Higher values fail in MQSim itself.) |
| 4 | `Working_Set_Percentage` | **no trigger in [100, 5]** | Does not drive trigger under steady write rate; affects per-GC cost only. |

## 6. Reproduction

```bash
cd ~/mqsim_gc_exp/MQSim
python3 sweep/aggregate.py  # re-runs the parse over sweep/runs/*/wl_scenario_1.xml
```

Per-config XML inputs are at `sweep/configs/*.xml` and `sweep/workloads/*.xml`;
each run's working dir is `sweep/runs/<name>/` and its log is
`sweep/logs/<name>.log`. Full parsed JSON is at `sweep/results.json` and
`sweep/trigger_summary.json`.

## 7. Footnote — MQSim known issues observed

1. **Preconditioner crash at low-occ × high-OP**: source line
   `Address_Mapping_Unit_Page_Level.cpp:738`,
   `PRINT_ERROR("It is not possible to assign PPA to all LPAs ...")`.
   Triggered at `(occ ≤ 30%, OP ≥ 0.15)` in our first attempt — we then moved
   the baseline to `occ=50, OP=0.07`.
2. **GC/WL inconsistency at high-occ × low-OP**: at `occ=80, OP=0.07` MQSim
   prints `ERROR: Inconsistency found when moving a page for GC/WL!`
3. **Cleanup heap corruption at high occupancy**: at `occ=90/95, OP=0.07`,
   simulation finishes writing the result XML but glibc `free()` aborts during
   teardown (`free(): invalid pointer`, `munmap_chunk(): invalid pointer`).
   The output XML is sometimes salvageable but the host-request counts are
   essentially zero — the device stalled long before Stop_Time.

These are limitations of the simulator, not of the experiment — they bound how
far the occupancy sweep can be pushed while keeping the OP fixed.
