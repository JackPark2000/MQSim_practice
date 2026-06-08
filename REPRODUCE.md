# Reproduction Guide

How to rebuild every result in [`REPORT.md`](REPORT.md) from this repo.

## Prerequisites

```text
Linux x86_64  (tested on Ubuntu 20.04, kernel 5.15)
g++ 11+       (tested with 11.4.0)
GNU Make      (tested with 4.2.1)
Python 3.8+   (only for sweep config generation + result aggregation)
pip:          numpy, matplotlib   (only for heatmap/line-plot rendering)
```

Disk: ~10 GB free (peak; sweep + exp2 working dirs hold per-run binaries +
output XMLs during runs).

Memory: per MQSim instance peaks at ~5-10 GB RSS (depends on occupancy &
working set). The repo's parallel launchers default to JOBS=4-6 — adjust
downward if memory-constrained.

## 1. Build MQSim

```bash
git clone https://github.com/JackPark2000/MQSim_practice.git
cd MQSim_practice
make clean && make           # produces ./MQSim
```

## 2. Phase 1 — verification run (~12 min, 2-way parallel)

```bash
mkdir -p run_baseline run_target
cp MQSim exp_configs/ssd_baseline_occ50.xml exp_workloads/wl_baseline_occ50.xml run_baseline/
cd run_baseline && mv ssd_baseline_occ50.xml ssd.xml && mv wl_baseline_occ50.xml wl.xml && cd ..
cp MQSim exp_configs/ssd_target_occ95.xml   exp_workloads/wl_target_occ95.xml   run_target/
cd run_target   && mv ssd_target_occ95.xml   ssd.xml && mv wl_target_occ95.xml   wl.xml && cd ..

( cd run_baseline && ./MQSim -i ssd.xml -w wl.xml > ../logs/baseline.log 2>&1 ) &
( cd run_target   && ./MQSim -i ssd.xml -w wl.xml > ../logs/target.log   2>&1 ) &
wait
cp run_baseline/wl_scenario_1.xml results/baseline_occ50_thr05.xml
cp run_target/wl_scenario_1.xml   results/target_occ95_thr05.xml
```

The exact XML inputs used are committed in `exp_configs/` and
`exp_workloads/`. Expected outputs are committed in `results/`; re-running
overwrites them.

## 3. Phase 2 — first parameter sweep (17 configs, ~25 min @ 4-way)

```bash
# Configs already generated and committed:
ls sweep/configs/    # 17 ssd_*.xml
ls sweep/workloads/  # 17 wl_*.xml

# Stage per-run dirs (copies MQSim + ssd.xml + wl.xml into each runs/<name>/)
python3 - <<'PY'
import json, shutil, os
manifest = json.load(open("sweep/manifest.json"))
for name in manifest:
    rd = f"sweep/runs/{name}"
    os.makedirs(rd, exist_ok=True)
    shutil.copy("MQSim", f"{rd}/MQSim")
    shutil.copy(f"sweep/configs/ssd_{name}.xml",   f"{rd}/ssd.xml")
    shutil.copy(f"sweep/workloads/wl_{name}.xml",  f"{rd}/wl.xml")
PY

# Run all 17, then aggregate
bash sweep/run_all.sh > sweep/run_all.out 2>&1
python3 sweep/aggregate.py | tee sweep/aggregate.out
```

Produces:
- `sweep/runs/<name>/wl_scenario_1.xml` — per-run MQSim output
- `sweep/results.json` — parsed metrics
- `sweep/trigger_summary.json` — per-parameter trigger map
- `sweep/SWEEP.md` already in repo summarizes the expected numbers

Adjust parallelism: `JOBS=8 bash sweep/run_all.sh ...` (default 4).

## 4. Phase 3 — follow-up experiments A + B + C (23 new + 11 reused, ~25 min @ 6-way)

```bash
# Stage new exp2 configs (skip reused ones — see exp2/manifest.json)
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

# Run the 23 new ones; aggregate; render heatmaps
JOBS=6 bash exp2/run_all.sh > exp2/run_all.out 2>&1
python3 exp2/aggregate.py | tee exp2/aggregate.out

# Optional: render the heatmap PNGs (committed under exp2/heatmap_*.png)
pip install --user numpy matplotlib
python3 scripts/render_heatmaps.py    # see file for code
python3 scripts/render_lineplots.py
```

### Known MQSim seed-flakes you may hit

Two cells use non-default seeds because the default MQSim seed (798/321) trips
known race-condition bugs in `GC_and_WL_Unit_Page_Level.cpp`:

| Cell | Default-seed error | Fix encoded in repo |
| --- | --- | --- |
| `exp2/runs/A_occ60/` | `Inconsistency found when moving a page for GC/WL!` | workload Seed=12345, SSD Seed=12346 |
| `exp2/runs/C_thr0p05_op0p02/` | `Illegal operation: Unlocking an LPA that has not been locked!` | workload Seed=67890, SSD Seed=67891 |

The committed `ssd.xml`/`wl.xml` for those cells already have the working
seeds; no manual intervention needed.

## 5. Verify against committed results

```bash
# Compare your fresh outputs against the committed canonical ones
diff <(python3 sweep/aggregate.py 2>&1) sweep/aggregate.out
diff <(python3 exp2/aggregate.py  2>&1) exp2/aggregate.out
```

Small numerical drift (sub-1 µs in latency) is fine — same seed should
otherwise give bit-identical TR-queue counts and FTL `Total_GC_Executions`.

## 6. What's where

```
MQSim_practice/
├── README.md                     ← upstream MQSim README (unmodified)
├── REPORT.md                     ← consolidated report (all phases)
├── REPRODUCE.md                  ← this file
├── Makefile, MQSim.sln, *.vcxproj, src/, fast18/, traces/
│                                 ← MQSim source (cloned from CMU-SAFARI, unmodified)
├── ssdconfig.xml, workload.xml   ← upstream defaults (unmodified)
├── exp_configs/                  ← Phase 1 SSD configs (2 XMLs)
├── exp_workloads/                ← Phase 1 workload configs (2 XMLs)
├── results/                      ← Phase 1 outputs + SUMMARY.md
├── run_baseline/, run_target/    ← Phase 1 working dirs (ssd.xml, wl.xml, output)
│                                 (MQSim binary is regenerated by `make`)
├── sweep/
│   ├── SWEEP.md                  ← Phase 2 report
│   ├── configs/ workloads/       ← 17 SSD + 17 workload XMLs
│   ├── runs/<name>/              ← per-run dirs (ssd.xml, wl.xml, output XML)
│   ├── logs/                     ← MQSim stdout/stderr
│   ├── manifest.json results.json trigger_summary.json
│   ├── aggregate.py aggregate.out
│   └── run_all.sh
├── exp2/
│   ├── EXP2.md  EXP2_A.md  EXP2_B.md  EXP2_C.md
│   ├── configs/ workloads/       ← 23 new SSD + 23 new workload XMLs
│   ├── runs/<name>/              ← 34 dirs (11 are XML copies from sweep/)
│   ├── logs/  manifest.json  to_run.json  results.json  summaries.json
│   ├── aggregate.py
│   ├── run_all.sh
│   ├── heatmap_*.png             ← 5 rendered heatmaps (Phase 3C)
│   └── plot_A_occ_refined.png plot_B_ws_costshaper.png
└── .gitignore                    ← build artifacts + per-run MQSim binary copies
```

## 7. What is NOT committed (gitignored)

- `build/`, `*.o`, top-level `MQSim` binary — regenerated by `make`
- `sweep/runs/*/MQSim` and `exp2/runs/*/MQSim` — per-run binary copies, regenerated by the staging snippet in §3 / §4
- editor / OS junk

All XML inputs, output XMLs, logs, manifests, aggregator scripts, and reports
*are* committed — so the result tables and plots in REPORT.md can be
re-aggregated and re-rendered without re-running MQSim.
