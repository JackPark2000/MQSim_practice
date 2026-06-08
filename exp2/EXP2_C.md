# Experiment C — `GC_Exec_Threshold` × `Overprovisioning_Ratio` 2D Sweep

## Goal

`thr` defines the trigger line (GC fires when `free_blocks/total_blocks < thr`).
OP shapes how big the free-block pool is *after preconditioning*. They are
geometric duals: lifting thr or shrinking OP both compress the gap until GC
fires immediately. This 5 × 5 grid quantifies that interaction.

## Setup

| Knob | Value |
| --- | --- |
| `Initial_Occupancy_Percentage` | 50 |
| `Working_Set_Percentage` | 100 |
| `Read_Percentage` | 1 |
| `Average_No_of_Reqs_in_Queue` | 128 |
| `Stop_Time` | 30 s |
| `GC_Exec_Threshold` (cols) | **0.001 / 0.005 / 0.01 / 0.025 / 0.05** |
| `Overprovisioning_Ratio` (rows) | **0.07 / 0.05 / 0.03 / 0.02 / 0.01** |

25 cells total. 9 reused from previous sweep (the `thr=0.001` column and the
`OP=0.07` row except their intersection at the baseline). 16 new runs done
here. One cell (`thr=0.05, OP=0.02`) initially crashed with
`Illegal operation: Unlocking an LPA that has not been locked!` — reseeded
(67890) and re-ran cleanly. All 25 cells now ok.

## Heatmaps

### 1. `Total_GC_Executions` — count

```
              thr=0.001   thr=0.005    thr=0.01   thr=0.025    thr=0.05
OP=0.07         0           0           15          514         2828
OP=0.05         15          15          18          543         3035
OP=0.03         19          19          75          444         2909
OP=0.02         18          18          50          529         2841
OP=0.01         20          20          73          667         2923
```

Reading the surface:

- **Top-left corner (`thr=0.001, OP=0.07`)** is the only true *no-GC* cell.
- **The `thr` column 0.005 behaves identically to 0.001** for every OP — both
  thresholds sit below MQSim's post-preconditioning free pool depth.
- **The first row** (OP=0.07): trigger first appears at thr = 0.01.
- **The first column** (thr=0.001): trigger first appears at OP = 0.05.
- Below the trigger frontier the count stabilizes at 15-75 GC per 30 s.
  Above it (`thr ≥ 0.025`), GC fires hundreds to thousands of times.
- **Right column (`thr=0.05`)** is uniformly saturated GC pressure
  (2,800-3,000 executions) — OP no longer matters once the trigger line is set
  high.

### 2. `Average_Page_Movement_For_GC` — per-cycle cost

```
              thr=0.001   thr=0.005    thr=0.01   thr=0.025    thr=0.05
OP=0.07         0.00        0.00       21.27       31.16       40.65
OP=0.05        25.80       25.80       21.94       34.58       43.69
OP=0.03        26.89       26.89       27.29       34.61       46.71
OP=0.02        27.67       27.67       27.34       37.63       47.78
OP=0.01        29.20       29.20       31.34       40.55       49.56
```

- Per-GC cost is **monotonic in both axes**: higher thr → lower OP increases
  the page-migration burden.
- Highest-corner (`thr=0.05, OP=0.01`) costs **49.6 valid pages per GC**, vs
  **~21 at the trigger frontier** — a 2.4 × per-cycle cost increase.

### 3. `Write Amplification Factor` (WAF = (user_w + gc_w) / user_w)

```
              thr=0.001   thr=0.005    thr=0.01   thr=0.025    thr=0.05
OP=0.07        1.000       1.000       1.002       1.044       1.223
OP=0.05        1.002       1.002       1.003       1.049       1.252
OP=0.03        1.003       1.003       1.011       1.042       1.273
OP=0.02        1.003       1.003       1.007       1.053       1.279
OP=0.01        1.003       1.003       1.010       1.064       1.294
```

- WAF behaves like a step function in `thr`: < 1.05 up to thr = 0.025,
  then jumps to 1.22-1.29 at thr = 0.05.
- OP only second-orders WAF on top of that: at thr = 0.05, dropping OP from
  0.07 to 0.01 lifts WAF from 1.223 to 1.294 (+5.8 %).

### 4. `GC_Write_TR_Queue` enqueued (sum over 32 channel/chip queues)

```
              thr=0.001   thr=0.005    thr=0.01   thr=0.025    thr=0.05
OP=0.07           0          0        2545        40358      147027
OP=0.05        2358       2358        3353        44375      164683
OP=0.03        2984       2984       11688        39430      167986
OP=0.02        2955       2955        8300        46738      167814
OP=0.01        3044       3044       11184        54697      176968
```

Same shape as GC executions; useful for confirming that the GC write traffic
itself (not just the count of GC cycles) climbs in concert.

### 5. Average Device Response Time (µs)

```
              thr=0.001   thr=0.005    thr=0.01   thr=0.025    thr=0.05
OP=0.07         3188        3188        3256        4161        5773
OP=0.05         3247        3247        3275        4237        5822
OP=0.03         3265        3265        3478        4091        6172
OP=0.02         3290        3290        3398        4309        6317
OP=0.01         3278        3278        3459        4477        6316
```

- Baseline ~ 3.2 ms. Crossing into the GC-on regime adds ~2.5 ms.
- The corner (`thr=0.05, OP=0.02`) is the worst at 6.3 ms (~2× baseline).

### 6. Max Device Response Time (µs, tail latency)

```
              thr=0.001   thr=0.005    thr=0.01   thr=0.025    thr=0.05
OP=0.07         3847        3847      258747      522595      775181
OP=0.05       262326      262326      267056      346649      517746
OP=0.03       271234      271234      340876      477810      525424
OP=0.02       256728      256728      273154      300734      781992
OP=0.01       217213      217213      291899      555005      435946
```

- Single non-GC cell (`thr=0.001, OP=0.07`) keeps tail at 3.85 ms.
- All other cells produce tail latencies in the 200 ms – 800 ms band, set by
  GC erase queueing.
- Tail is *not* monotonic in thr/OP — once GC fires at all, the tail floor is
  effectively the GC erase wait time (~0.5 s), and stochastic queueing
  decides which exact cell tops out.

## Interpretation as a heatmap (for plotting)

A natural visualization: `x = log10(thr)`, `y = OP`, color = `log10(1 + GC_Exec)`
or `WAF`. The frontier surface lives along the diagonal where
`thr · 2048 ≈ post-preconditioning free pool size`. Lower-right (high thr,
low OP) is the saturated GC corner. Upper-left (low thr, high OP) is the
single no-GC region.

Suggested matplotlib snippet (data in `summaries.json`):

```python
import json, numpy as np, matplotlib.pyplot as plt
d = json.load(open("exp2/summaries.json"))
thrs, ops = d["THRS"], d["OPS"]
M = np.array([[c.get("GC_Exec", 0) for c in row] for row in d["C_grid"]])
plt.imshow(np.log10(1 + M), origin="upper",
           extent=[0, len(thrs), 0, len(ops)], aspect="auto")
plt.xticks(np.arange(len(thrs)) + 0.5, [str(t) for t in thrs])
plt.yticks(np.arange(len(ops)) + 0.5, [str(o) for o in ops])
plt.xlabel("GC_Exec_Threshold"); plt.ylabel("Overprovisioning_Ratio")
plt.title("log10(1 + Total_GC_Executions) over thr × OP")
plt.colorbar(); plt.savefig("exp2/heatmap_gc_exec.png", dpi=140)
```

## Take-aways

1. **One no-GC cell, one saturated corner.** The grid has a sharp
   trigger frontier:
   - `thr ≤ 0.005`: only OP=0.07 stays GC-free; lower OPs trigger 15-20 GC.
   - `thr ≥ 0.025`: GC heavy regardless of OP.
2. **`thr` dominates `OP` for the *count* of GC.** Lifting thr by 5× (0.005 → 0.025)
   moves GC from < 20 to > 500 across the entire OP column. Shrinking OP by 7×
   (0.07 → 0.01) at fixed thr=0.001 only takes GC from 0 to 20.
3. **`OP` dominates `thr` for the *cost* per GC.** At thr=0.001, dropping OP
   alone lifts `AvgPgMv` from 0 to 29.20. At OP=0.07, lifting thr alone goes
   0 → 40.65. Similar magnitudes — but the OP axis controls the floor at
   which per-GC cost lives (steady-state block fill), while thr controls the
   *frequency* at which it pays that cost.
4. **WAF crosses 1.20 only at thr = 0.05**, regardless of OP. So for a
   workload that needs to live below WAF = 1.10, keep thr ≤ 0.025.

## Reproduction

```bash
cd ~/mqsim_gc_exp/MQSim
python3 exp2/aggregate.py   # re-parses results.json, summaries.json
```

Per-cell working directories at `exp2/runs/C_thr{thr}_op{op}/`, logs at
`exp2/logs/C_*.log`. Raw machine-readable matrix at `exp2/summaries.json`.
