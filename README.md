# MQSim GC Trigger Sweep — Reproducer

End-to-end reproduction of an experimental study on what makes MQSim's
garbage collector fire. Builds MQSim, sweeps four FTL/workload parameters
individually to locate per-parameter GC trigger points, then refines the
occupancy boundary and runs a 2-D `GC_Exec_Threshold` × `Overprovisioning_Ratio`
heatmap.

Full analysis with all measured numbers and discussion: [`REPORT.md`](REPORT.md).

## What you'll reproduce

| Experiment | Question | Headline result | Key plot |
| --- | --- | --- | --- |
| **Phase 2** — 4 single-parameter sweeps from a true no-GC baseline | At which value of each knob does GC first fire? | `thr=0.01`, `OP=0.05`, `occ=70` (refined to **55** in Phase 3A), `ws=no trigger` | `sweep/plot_thr_sweep.png`, `sweep/plot_op_sweep.png` |
| **Phase 3A** — occupancy boundary refinement | What's the exact occupancy trigger between 50 and 70? | **occ = 55**, smooth ramp through 70 | `exp2/plot_A_occ_refined.png` |
| **Phase 3B** — working-set under GC-on conditions | If working-set isn't a trigger driver, what is it? | **GC cost shaper**: AvgPgMv 40.65 → 35.01, WAF 1.223 → 1.193 as ws 100 → 5 | `exp2/plot_B_ws_costshaper.png` |
| **Phase 3C** — `GC_Exec_Threshold` × `Overprovisioning_Ratio` 2-D | How do `thr` and OP interact? | One no-GC corner (`thr=0.001, OP=0.07`), one saturated corner (`thr=0.05, OP=0.01`: GC=2,923, WAF=1.294) | `exp2/heatmap_*.png` (5 PNGs) |

## Prerequisites

```
Linux x86_64        (tested on Ubuntu 20.04, kernel 5.15)
g++ 11+             (tested with 11.4.0)
GNU Make            (tested with 4.2.1)
Python 3.8+         (sweep config generation + result aggregation)
numpy, matplotlib   (only for re-rendering heatmaps / line plots)
```

Disk ~10 GB free (peak; sweep + exp2 working dirs hold per-run MQSim
binaries during runs). Memory: per-instance peaks at ~5-10 GB RSS. The
parallel launchers default to `JOBS=4-6` — lower if memory-constrained.

## 1. Build MQSim

```bash
git clone https://github.com/JackPark2000/MQSim_practice.git
cd MQSim_practice
make clean && make            # produces ./MQSim
```

Source tree (`src/`, `Makefile`, `*.vcxproj`, `fast18/`, `traces/`,
`ssdconfig.xml`, `workload.xml`) is unmodified upstream MQSim — no patches.

## 2. Phase 2 — 4 single-parameter sweeps (17 configs, ~25 min @ 4-way)

Starting from a verified **no-GC baseline**
(`occ=50, ws=100, GC_Exec_Threshold=0.001, OP=0.07, Read%=1, QD=128, Stop=30s`),
sweep each knob independently until GC first triggers.

| Sweep | Values | What it tests |
| --- | --- | --- |
| `Initial_Occupancy_Percentage` | 50 / 70 / 80 / 90 / 95 | trigger by tightening occupancy |
| `Working_Set_Percentage` | 100 / 50 / 20 / 10 / 5 | (none — confirmed; see Phase 3B for the right setup) |
| `GC_Exec_Threshold` | 0.001 / 0.005 / 0.01 / 0.025 / 0.05 | direct trigger knob |
| `Overprovisioning_Ratio` | 0.07 / 0.05 / 0.03 / 0.02 / 0.01 | indirect trigger via post-precondition free pool |

17 unique configs (baseline shared across all four sweeps).

```bash
# 17 ssd_*.xml and 17 wl_*.xml are already committed:
ls sweep/configs/    # 17 SSD XMLs
ls sweep/workloads/  # 17 workload XMLs

# Stage per-run dirs (copies MQSim + ssd.xml + wl.xml into each runs/<name>/)
# Per-run dirs are required because MQSim writes wl_scenario_<n>.xml into the
# workload file's directory; running in parallel from one dir would collide.
python3 - <<'PY'
import json, shutil, os
manifest = json.load(open("sweep/manifest.json"))
for name in manifest:
    rd = f"sweep/runs/{name}"
    os.makedirs(rd, exist_ok=True)
    shutil.copy("MQSim", f"{rd}/MQSim")
    shutil.copy(f"sweep/configs/ssd_{name}.xml",  f"{rd}/ssd.xml")
    shutil.copy(f"sweep/workloads/wl_{name}.xml", f"{rd}/wl.xml")
PY

# Run all 17 in parallel and aggregate
bash sweep/run_all.sh > sweep/run_all.out 2>&1
python3 sweep/aggregate.py | tee sweep/aggregate.out
```

Adjust parallelism: `JOBS=8 bash sweep/run_all.sh ...` (default 4).

Produces:
- `sweep/runs/<name>/wl_scenario_1.xml` — per-run MQSim output
- `sweep/results.json` — parsed metrics
- `sweep/trigger_summary.json` — per-parameter trigger map
- `sweep/SWEEP.md` (committed) — expected numbers for comparison

### MQSim crashes in this sweep

`Initial_Occupancy_Percentage ≥ 80` with `OP=0.07` trips known MQSim bugs
(`Inconsistency found when moving a page for GC/WL!`,
 `free(): invalid pointer` on shutdown). The occupancy trigger boundary is
therefore captured at finer granularity in Phase 3A below, where occ stays
in the working range.

## 3. Phase 3 — follow-up experiments A + B + C (23 new + 11 reused, ~25 min @ 6-way)

Three sub-experiments designed from the Phase-2 results:

- **3A** refines the occupancy trigger boundary at 5-pp resolution
  (occ = 55 / 60 / 65 / 70).
- **3B** re-runs the working-set sweep under `thr=0.05` so GC always fires —
  testing the hypothesis that working set shapes per-GC *cost* rather than
  trigger.
- **3C** runs the full 5 × 5 grid of `GC_Exec_Threshold` × `Overprovisioning_Ratio`.

Of 34 cells, **11 are reused** from Phase 2's outputs (manifest tracks
which); only **23 new MQSim runs** are needed.

```bash
# Stage exp2 run dirs. New cells get MQSim+ssd+wl; reused cells get the
# Phase-2 output XML copied in directly.
python3 - <<'PY'
import json, shutil, os
manifest = json.load(open("exp2/manifest.json"))
for name, m in manifest.items():
    rd = f"exp2/runs/{name}"
    os.makedirs(rd, exist_ok=True)
    if m["status"] == "REUSED":
        src = f"sweep/runs/{m['reused_from']}/wl_scenario_1.xml"
        shutil.copy(src, f"{rd}/wl_scenario_1.xml")
        continue
    shutil.copy("MQSim", f"{rd}/MQSim")
    shutil.copy(f"exp2/configs/ssd_{name}.xml",  f"{rd}/ssd.xml")
    shutil.copy(f"exp2/workloads/wl_{name}.xml", f"{rd}/wl.xml")
PY

# Run the 23 new ones, aggregate
JOBS=6 bash exp2/run_all.sh > exp2/run_all.out 2>&1
python3 exp2/aggregate.py | tee exp2/aggregate.out
```

### Re-rendering the plots (optional)

The committed PNGs are produced by the snippets below. They read `sweep/results.json`
and `exp2/results.json` / `exp2/summaries.json` so they regenerate even
without re-running MQSim.

```bash
pip install --user numpy matplotlib

# Phase 2 line plots (4 PNGs in sweep/)
python3 scripts/render_lineplots.py   # see file; same code that produced committed PNGs

# Phase 3A occupancy-refined plot (with trigger=55 highlight)
# Phase 3B working-set cost-shaper plot (6 panels)
# Phase 3C 5 heatmaps
python3 scripts/render_heatmaps.py    # see file
```

### Known MQSim seed-flakes (already handled in committed configs)

Two cells use non-default seeds because the default MQSim seed (798/321) trips
known race conditions in `GC_and_WL_Unit_Page_Level.cpp`:

| Cell | Default-seed error | Seed encoded in committed XMLs |
| --- | --- | --- |
| `exp2/runs/A_occ60/`         | `Inconsistency found when moving a page for GC/WL!`        | workload Seed=12345, SSD Seed=12346 |
| `exp2/runs/C_thr0p05_op0p02/`| `Illegal operation: Unlocking an LPA that has not been locked!` | workload Seed=67890, SSD Seed=67891 |

No manual intervention needed — the committed `ssd.xml`/`wl.xml` for those
cells already carry the working seeds.

## 4. Verify against committed results

```bash
# Compare your fresh aggregate output against the canonical one
diff <(python3 sweep/aggregate.py 2>&1) sweep/aggregate.out
diff <(python3 exp2/aggregate.py  2>&1) exp2/aggregate.out
```

Same seeds should give bit-identical TR-queue counts and FTL
`Total_GC_Executions`. Sub-µs drift in average latency is expected from
floating-point scheduling.

## 5. Repository layout

```
MQSim_practice/
├── README.md                     ← this file (reproducer)
├── REPORT.md                     ← consolidated report (all phases, all numbers)
├── Makefile, MQSim.sln, *.vcxproj, src/, fast18/, traces/
│                                 ← MQSim source (cloned from CMU-SAFARI, unmodified)
├── ssdconfig.xml, workload.xml   ← upstream defaults (unmodified)
│
├── sweep/                        ← Phase 2 artifacts
│   ├── SWEEP.md                  ← Phase 2 detailed report
│   ├── configs/   ssd_*.xml      ← 17 SSD configs
│   ├── workloads/ wl_*.xml       ← 17 workload configs
│   ├── runs/<name>/              ← per-run dirs (ssd.xml, wl.xml, wl_scenario_1.xml)
│   ├── logs/<name>.log           ← MQSim stdout/stderr
│   ├── manifest.json results.json trigger_summary.json
│   ├── aggregate.py aggregate.out run_all.sh
│   └── plot_*.png                ← 4 line plots (occ / ws / thr / OP)
│
├── exp2/                         ← Phase 3 artifacts
│   ├── EXP2.md EXP2_A.md EXP2_B.md EXP2_C.md
│   ├── configs/ workloads/       ← 23 new SSD + 23 new workload XMLs
│   ├── runs/<name>/              ← 34 dirs (11 hold reused XMLs from sweep/)
│   ├── logs/  manifest.json  to_run.json  results.json  summaries.json
│   ├── aggregate.py aggregate.out run_all.sh
│   ├── heatmap_*.png             ← 5 Phase-3C heatmaps
│   └── plot_A_occ_refined.png plot_B_ws_costshaper.png
│
└── .gitignore                    ← build artifacts + per-run MQSim binary copies
```

## 6. What is NOT committed (gitignored)

- `build/`, `*.o`, top-level `MQSim` binary — regenerated by `make`
- `sweep/runs/*/MQSim` and `exp2/runs/*/MQSim` — per-run binary copies (~17 MB
  each × ~40 dirs ≈ 700 MB), regenerated by the staging snippets in §2 / §3
- editor / OS junk

All XML inputs, output XMLs, logs, manifests, aggregator scripts, and reports
*are* committed — so the result tables and plots in REPORT.md can be
re-aggregated and re-rendered without re-running MQSim.
