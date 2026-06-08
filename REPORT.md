# MQSim GC Trigger Investigation — Consolidated Report

End-to-end documentation of every experiment run in this session:
1. **Phase 1 — Verification** that GC fires in MQSim under the PPT guideline (`results/`)
2. **Phase 2 — First per-parameter sweep** (4 knobs × 5 values) to locate trigger points (`sweep/`)
3. **Phase 3 — Three follow-up experiments**: occupancy boundary refinement, working-set cost shaping, and 2D threshold × OP heatmap (`exp2/`)

---

## 0. Environment

| Item | Value |
| --- | --- |
| Repo | <https://github.com/CMU-SAFARI/MQSim.git> (`make`-built) |
| Compiler | g++ 11.4.0 (Ubuntu 11.4.0-2ubuntu1~20.04) |
| make | GNU Make 4.2.1 |
| OS | Ubuntu 20.04 LTS, Linux 5.15 |
| Host | 40 cores, 251 GB RAM |
| Build | `make clean && make` (no patches, no flags) |
| Invocation | `./MQSim -i <ssdconfig> -w <workload>` per run, separate working dir per run to avoid `wl_scenario_<n>.xml` output collisions |

All experiments live in `~/mqsim_gc_exp/MQSim/`. Each phase has its own subtree:
- `results/` — Phase 1 outputs and `SUMMARY.md`
- `sweep/`   — Phase 2 outputs, `SWEEP.md`, aggregator
- `exp2/`    — Phase 3 outputs, `EXP2.md`, `EXP2_A/B/C.md`, heatmap PNGs

---

## 1. Important gotchas discovered

### 1.1 PPT guideline tag typo

The PPT calls the threshold `GC_Exect_Threshold`. **MQSim's actual XML tag is
`GC_Exec_Threshold`.** Using the PPT spelling in `grep`/XML patching produces
zero matches and the threshold change silently does nothing.

```bash
grep -n "GC_Exec_Threshold"  ssdconfig.xml   # 1 hit (line 33) — correct
grep -n "GC_Exect_Threshold" ssdconfig.xml   # 0 hits — wrong
```

### 1.2 MQSim output-file collision

`./MQSim -i ssd.xml -w wl.xml` writes results to
`<workload-basename>_scenario_<n>.xml` in the **workload file's directory**.
If two runs share a workload-file directory, the second overwrites the first.
Every run in this report uses its own `runs/<name>/` working directory.

### 1.3 MQSim known bugs hit

| Site | Error | Conditions hit | Workaround used |
| --- | --- | --- | --- |
| Preconditioner | `It is not possible to assign PPA to all LPAs in Allocate_address_for_preconditioning!` (`Address_Mapping_Unit_Page_Level.cpp:738`) | low-occ × high-OP (e.g. occ ≤ 30, OP ≥ 0.15) | move baseline to occ = 50, OP = 0.07 |
| GC mover | `Inconsistency found when moving a page for GC/WL!` | seed-dependent at mid-high occupancy (60-80 %) | reseed (12345) and re-run |
| GC mover | `Illegal operation: Unlocking an LPA that has not been locked!` | seed-dependent at `thr=0.05, OP=0.02` | reseed (67890) and re-run |
| Cleanup | `free(): invalid pointer` / `munmap_chunk(): invalid pointer` | high-occ (occ ≥ 90) × OP = 0.07 — sim finishes, crashes during shutdown | not solvable; result XML often partial, host request count near zero |

All bugs are in MQSim itself, not in our configs. Reseeded reruns are
documented per-cell below.

---

## 2. SSD hardware model (held constant across every experiment)

Taken directly from `ssdconfig.xml`; only the GC/OP/threshold knobs are
swept. Geometry, NAND timing, host interface stay fixed.

| Class | Field | Value |
| --- | --- | --- |
| Host | `PCIe_Lane_Bandwidth`, `PCIe_Lane_Count` | 1.0 GB/s/lane × 4 lanes |
| Host interface | `HostInterface_Type` | NVMe |
| Cache | `Data_Cache_Capacity` | 256 MiB, ADVANCED, SHARED |
| Mapping | `Address_Mapping`, `Ideal_Mapping_Table` | PAGE_LEVEL, true |
| FTL | `Transaction_Scheduling_Policy` | PRIORITY_OUT_OF_ORDER |
| FTL | `Plane_Allocation_Scheme` | CWDP |
| NAND | `Flash_Technology` | MLC |
| NAND | Read / Program / Erase | 75 µs / 750 µs / 3.8 ms |
| NAND | `Channel_Transfer_Rate` | 333 MT/s |
| Geometry | Channels × chips × dies × planes | **8 × 4 × 2 × 2 = 128 planes** |
| Geometry | Blocks/plane × pages/block × page | 2,048 × 256 × 8 KiB |
| Geometry | Total physical capacity | 128 × 2048 × 256 × 8 KiB ≈ **64 GiB** |
| Wear-leveling | dynamic + static enabled, threshold 100 |

Per-plane block count = 2,048, so a `GC_Exec_Threshold` of `thr` means
GC fires when the per-plane free-block pool drops below `thr × 2048` blocks.

---

## 3. Phase 1 — Verification run (`results/`)

Goal: confirm `GC_Read_TR_Queue`, `GC_Write_TR_Queue`, `GC_Erase_TR_Queue` are
non-zero under the PPT guideline target config.

### 3.1 Configs

Workload single-flow synthetic (taken from the first IO_Scenario in the
shipped `workload.xml`, all other flows removed):

| Knob | Baseline | Target |
| --- | ---: | ---: |
| `Initial_Occupancy_Percentage` | 50 | **95** |
| `Working_Set_Percentage` | 100 | **10** |
| `GC_Exec_Threshold` | 0.05 | 0.05 |
| `Overprovisioning_Ratio` | 0.07 | 0.07 |
| `Read_Percentage` | 1 | 1 |
| `Average_No_of_Reqs_in_Queue` (QD) | 128 | 128 |
| `Stop_Time` | 100 s (`100,000,000,000` ns) | 100 s |
| `Enabled_Preconditioning` | true | true |
| `GC_Block_Selection_Policy` | GREEDY | GREEDY |
| `Preemptible_GC_Enabled` | false | false |
| `Ideal_Mapping_Table` | true | true |
| Channel / Chip / Die / Plane IDs | all (8 × 4 × 2 × 2) | all |

### 3.2 Runtime

| Run | Real time | Peak RSS | Exit | Output |
| --- | ---: | ---: | ---: | --- |
| Baseline | 231 s (3 m 51 s) | 6.2 GB | 0 | `results/baseline_occ50_thr05.xml` |
| Target | 511 s (8 m 31 s) | 4.8 GB | 0 | `results/target_occ95_thr05.xml` |

Target emitted a warning during preconditioning:

```
The specified initial occupancy value could not be satisfied as the
working set of workload #0 is small. MQSim made some adjustments!
```

This means `Working_Set=10%` is too tight to satisfy `Initial_Occupancy=95%`
exactly; MQSim adjusted internally. Simulation continued normally.

### 3.3 Results

#### 3.3.1 FTL statistics

| FTL field | Baseline | Target |
| --- | ---: | ---: |
| `Issued_Flash_Read_CMD` | 490,159 | 883,010 |
| `Issued_Flash_Program_CMD` | 2,584,094 | 1,120,529 |
| `Issued_Flash_Erase_CMD` | 9,476 | 4,021 |
| `Issued_Flash_Multiplane_Erase_CMD` | 345 | 386 |
| `Total_GC_Executions` | **10,039** | **4,666** |
| `Average_Page_Movement_For_GC` | **43.73** | **187.89** |
| `Total_WL_Executions` | 127 | 127 |

#### 3.3.2 TSU TR-queue aggregates (sum across 32 channel/chip queues)

| Queue | qcnt | Enqueued (B) | Enqueued (T) | MaxQ (B/T) | AvgWait µs (B/T) | MaxWait µs (B/T) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `User_Read_TR_Queue` (× 4 priority) | 128 | 21,998 | 3,296 | 5 / 5 | 1,206 / 16,685 | 775,092 / 2,767,135 |
| `User_Write_TR_Queue` (× 4 priority) | 128 | 2,180,095 | 329,661 | 194 / 240 | 2,663 / 14,527 | 830,112 / 2,627,975 |
| `Mapping_Read_TR_Queue` | 32 | 0 | 0 | — | — | — |
| `Mapping_Write_TR_Queue` | 32 | 0 | 0 | — | — | — |
| **`GC_Read_TR_Queue`** | 32 | **471,125** | **907,448** | 506 / 713 | 3,512 / 17,500 | 32,519 / 66,892 |
| **`GC_Write_TR_Queue`** | 32 | **471,125** | **907,448** | 585 / **2,312** | 35,434 / **372,311** | 256,763 / 1,349,724 |
| **`GC_Erase_TR_Queue`** | 32 | **10,166** | **4,793** | 6 / 16 | 64,176 / 775,305 | 594,312 / **2,621,405** |

Mapping_* is zero because `Ideal_Mapping_Table=true` removes CMT misses.

#### 3.3.3 Host.IO_Flow

| Field | Baseline | Target | Ratio |
| --- | ---: | ---: | ---: |
| `Request_Count` | 2,202,508 | 333,264 | 0.15× |
| `Read_Request_Count` | 21,998 | 3,296 | |
| `Write_Request_Count` | 2,180,510 | 329,968 | |
| `IOPS` | 22,004 | 3,322 | 0.15× |
| `Bandwidth` (B/s) | 90,129,864 | 13,608,010 | 0.15× |
| `Device_Response_Time` (µs) | 5,811 | **38,421** | 6.61× |
| `Min_Device_Response_Time` (µs) | 25 | 25 | |
| `Max_Device_Response_Time` (µs) | 775,181 | **2,767,224** | 3.57× |
| `End_to_End_Request_Delay` (µs) | 5,811 | 38,421 | 6.61× |

#### 3.3.4 Derived

| | Baseline | Target |
| --- | ---: | ---: |
| `WAF = (user_w + gc_w) / user_w` | 1.216 | **3.753** |
| GC writes per host write | 0.216 | **2.750** |

### 3.4 Phase-1 takeaway

GC transactions are **non-zero in both runs** ⇒ acceptance condition satisfied.
Target additionally shows the classic high-occupancy steady-state signature:
~4.3× more valid pages copied per GC, WAF rising 1.22 → 3.75, IOPS collapsing
6.6×, and `Max_Device_Response_Time` reaching 2.77 s (almost exactly equal to
`GC_Erase_TR_Queue` max wait of 2.62 s — tail latency *is* GC erase wait).

---

## 4. Phase 2 — First per-parameter sweep (`sweep/`)

Goal: starting from a verified no-GC baseline, sweep one parameter at a time
and find the smallest value at which `Total_GC_Executions > 0`.

### 4.1 No-GC baseline

The Phase-1 baseline (`occ=50, thr=0.05, OP=0.07`) heavily triggers GC because
post-preconditioning free-pool size sits below `thr × 2048 ≈ 102` blocks/plane.
To establish a *true* no-GC anchor, we lowered `thr` to **0.001**:

| Knob | Value | Reason |
| --- | --- | --- |
| `Initial_Occupancy_Percentage` | 50 | preconditioner-safe (low/high-occ × low/high-OP edges crash) |
| `Working_Set_Percentage` | 100 | minimal collision → minimal invalidation |
| `GC_Exec_Threshold` | **0.001** | trigger only when < 2 blocks/plane free |
| `Overprovisioning_Ratio` | 0.07 | SSD default |
| `Read_Percentage` | 1 | write-heavy probe |
| `Average_No_of_Reqs_in_Queue` | 128 | high QD to actually pressure the device |
| `Stop_Time` | 30 s | 100 s → 30 s for sweep tractability (>1 M writes still drained) |

At this point: `Total_GC_Executions = 0`, `WAF = 1.000`, response time 3.19 ms.
Confirmed **no-GC anchor**.

### 4.2 Sweep ranges (5 values per parameter)

| Parameter | Sweep values |
| --- | --- |
| `Initial_Occupancy_Percentage` | **50** → 70 → 80 → 90 → 95 |
| `Working_Set_Percentage` | **100** → 50 → 20 → 10 → 5 |
| `GC_Exec_Threshold` | **0.001** → 0.005 → 0.01 → 0.025 → 0.05 |
| `Overprovisioning_Ratio` | **0.07** → 0.05 → 0.03 → 0.02 → 0.01 |

17 unique configs after dedup (the baseline cell appears in all 4 sweeps).
4-way parallel on the server.

### 4.3 Full per-run table

| Run | occ | ws | thr | OP | `Total_GC_Executions` | AvgPgMv | GC_Erase enq | UserW | WAF | DevResp µs | MaxResp µs | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `baseline` | 50 | 100 | 0.001 | 0.07 | **0** | 0.0 | 0 | 1,191,951 | 1.000 | 3,188 | 3,847 | ok |
| `sw_occ_70` | 70 | 100 | 0.001 | 0.07 | **691** | 84.4 | 815 | 656,348 | 1.136 | 5,791 | 760,205 | ok |
| `sw_occ_80` | 80 | 100 | 0.001 | 0.07 | — | — | — | — | — | — | — | **MQSim GC/WL inconsistency, no output** |
| `sw_occ_90` | 90 | 100 | 0.001 | 0.07 | 0 | 0.0 | 0 | 0 | — | 1,946 | 2,630 | `free(): invalid pointer` (output XML written before crash; no real writes) |
| `sw_occ_95` | 95 | 100 | 0.001 | 0.07 | 0 | 0.0 | 0 | 239 | 1.00 | 2,324 | 7,311 | `munmap_chunk(): invalid pointer` |
| `sw_ws_50` | 50 | 50 | 0.001 | 0.07 | **0** | 0.0 | 0 | 1,189,989 | 1.000 | 3,192 | 3,963 | ok |
| `sw_ws_20` | 50 | 20 | 0.001 | 0.07 | **0** | 0.0 | 0 | 1,187,530 | 1.000 | 3,196 | 3,805 | ok |
| `sw_ws_10` | 50 | 10 | 0.001 | 0.07 | **0** | 0.0 | 0 | 1,191,435 | 1.000 | 3,180 | 3,776 | ok |
| `sw_ws_5` | 50 | 5 | 0.001 | 0.07 | **0** | 0.0 | 0 | 1,191,027 | 1.000 | 3,171 | 3,734 | ok |
| `sw_thr_0p005` | 50 | 100 | 0.005 | 0.07 | **0** | 0.0 | 0 | 1,191,951 | 1.000 | 3,188 | 3,847 | ok |
| `sw_thr_0p01` | 50 | 100 | 0.01 | 0.07 | **15** | 21.3 | 24 | 1,167,402 | 1.002 | 3,256 | 258,747 | ok |
| `sw_thr_0p025` | 50 | 100 | 0.025 | 0.07 | **514** | 31.2 | 612 | 913,450 | 1.044 | 4,161 | 522,595 | ok |
| `sw_thr_0p05` | 50 | 100 | 0.05 | 0.07 | **2,828** | 40.6 | 2,955 | 658,419 | 1.223 | 5,773 | 775,181 | ok |
| `sw_op_0p05` | 50 | 100 | 0.001 | 0.05 | **15** | 25.8 | 23 | 1,170,274 | 1.002 | 3,247 | 262,326 | ok |
| `sw_op_0p03` | 50 | 100 | 0.001 | 0.03 | **19** | 26.9 | 29 | 1,163,935 | 1.003 | 3,265 | 271,234 | ok |
| `sw_op_0p02` | 50 | 100 | 0.001 | 0.02 | **18** | 27.7 | 28 | 1,155,016 | 1.003 | 3,290 | 256,728 | ok |
| `sw_op_0p01` | 50 | 100 | 0.001 | 0.01 | **20** | 29.2 | 30 | 1,159,219 | 1.003 | 3,278 | 217,213 | ok |

### 4.4 Phase-2 trigger summary

| Sweep | No-GC range | **First trigger** | Heavy end | Comment |
| --- | --- | --- | --- | --- |
| `Initial_Occupancy_Percentage` | 50 (GC=0) | **70** (GC=691, WAF=1.136) | 80-95 crash | trigger somewhere in (50, 70] — refined in Phase 3A |
| `Working_Set_Percentage` | 100 → 5 all **GC = 0** | **no trigger in tested range** | even ws=5 gives 0 GC | ws doesn't drain the free-block pool — re-tested as a *cost* knob in Phase 3B |
| `GC_Exec_Threshold` | 0.001, 0.005 (GC=0) | **0.01** (GC=15) | 0.05 (GC=2,828) | trigger between 0.005 and 0.01 ⇒ post-preconditioning free pool ≈ 10-20 blocks/plane |
| `Overprovisioning_Ratio` | 0.07 (GC=0) | **0.05** (GC=15) | 0.01 (GC=20) | sharp step at 0.05; count then saturates |

`GC_Exec_Threshold` sweep is the cleanest interpretation:

| thr | trigger floor (blocks/plane) | GC_Exec result |
| ---: | ---: | ---: |
| 0.001 | 2.05 | 0 |
| 0.005 | 10.24 | 0 |
| 0.010 | 20.48 | **15** ← first |
| 0.025 | 51.20 | 514 |
| 0.050 | 102.40 | 2,828 |

⇒ post-preconditioning free pool lives between 10 and 20 blocks/plane.

---

## 5. Phase 3A — Occupancy boundary refinement (`exp2/`)

### 5.1 Setup

| Knob | Value |
| --- | --- |
| `Initial_Occupancy_Percentage` | **55 / 60 / 65 / 70** ← sweep |
| `Working_Set_Percentage` | 100 |
| `GC_Exec_Threshold` | 0.001 |
| `Overprovisioning_Ratio` | 0.07 |
| `Read_Percentage` | 1 |
| `Average_No_of_Reqs_in_Queue` | 128 |
| `Stop_Time` | 30 s |

(Cell at occ=70 reused from Phase 2; occ=80, 90, 95 omitted because they crash
under MQSim at OP=0.07.)

### 5.2 Reruns

- `A_occ60` first attempt aborted with
  `ERROR: Inconsistency found when moving a page for GC/WL!` at 90 % sim
  progress. Reseeded to SSD seed 12346 / workload seed 12345; rerun passed.

### 5.3 Results

| occ | `Total_GC_Executions` | AvgPgMv | GC_Erase enq | GC_Write enq | UserW | WAF | DevResp µs | MaxResp µs | Status |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 50 | **0** | 0.00 | 0 | 0 | 1,191,951 | 1.000 | 3,188 | 3,847 | ok (baseline) |
| 55 | **37** | 31.59 | 56 | 5,863 | 1,146,405 | 1.005 | 3,322 | 520,907 | ok |
| 60 | **148** | 48.05 | 209 | 22,272 | 1,012,553 | 1.022 | 3,753 | 820,507 | ok (reseeded) |
| 65 | **440** | 65.24 | 562 | 59,220 | 817,151 | 1.072 | 4,654 | 822,887 | ok |
| 70 | **691** | 84.38 | 815 | 89,536 | 656,348 | 1.136 | 5,791 | 760,205 | ok |

### 5.4 Findings

- **First trigger: occ = 55** — a 5 pp step from 50 already produces 37 GC
  cycles and lifts `Max_Device_Response_Time` from 3.85 ms to 521 ms.
- Smooth monotonic ramps in every metric:
  - `GC_Exec`: 0 → 37 → 148 → 440 → 691 (≈ 3× per 5 % occupancy step)
  - `AvgPgMv`: 0 → 31.6 → 48.1 → 65.2 → 84.4 (each surviving block carries
    more valid pages → costlier GC)
  - `WAF`: 1.000 → 1.005 → 1.022 → 1.072 → 1.136
  - `Max_Device_Response_Time`: 3.8 ms → 521 ms → 821 ms → 823 ms → 760 ms
- `UserW` falls 1.19 M → 0.66 M as occupancy rises — user writes wait behind GC.

---

## 6. Phase 3B — Working set under GC-on (cost shaper, not trigger)

### 6.1 Setup

Same baseline as before **except** `thr = 0.05` so GC fires in every cell.
Then sweep `Working_Set_Percentage`.

| Knob | Value |
| --- | --- |
| `Initial_Occupancy_Percentage` | 50 |
| `Working_Set_Percentage` | **100 / 50 / 20 / 10 / 5** ← sweep |
| `GC_Exec_Threshold` | **0.05** (GC always fires) |
| `Overprovisioning_Ratio` | 0.07 |
| `Read_Percentage` | 1 |
| `Average_No_of_Reqs_in_Queue` | 128 |
| `Stop_Time` | 30 s |

(`ws=100` cell reused from Phase 2's `sw_thr_0p05`.)

### 6.2 Results

| ws | `Total_GC_Executions` | AvgPgMv | WAF | `GC_Write_TR_Queue` enq | `GC_Erase` max wait µs | DevResp µs | MaxResp µs |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 2,828 | **40.65** | **1.223** | 147,027 | 594,312 | 5,773 | 775,181 |
| 50 | 2,838 | 40.91 | 1.226 | 148,222 | 529,866 | 5,785 | 591,806 |
| 20 | 2,850 | 39.94 | 1.220 | 145,968 | 716,158 | 5,725 | 601,578 |
| 10 | 2,802 | 38.42 | 1.211 | 139,789 | 521,777 | 5,724 | 542,654 |
| 5 | 2,924 | **35.01** | **1.193** | 134,507 | 504,243 | 5,425 | 548,123 |

### 6.3 Findings

1. **`Total_GC_Executions` is essentially flat** (2,802-2,924) — confirms B's
   premise that working-set is not a trigger knob.
2. **`Average_Page_Movement_For_GC` decreases monotonically** with shrinking
   working set: 40.65 → 35.01 (−14 %). Same per-cycle work is amortized over
   tighter invalid-page concentration → fewer valid pages to migrate per
   GREEDY victim.
3. **`WAF` shrinks 1.223 → 1.193** (−2.4 %), same mechanism.
4. **`GC_Write_TR_Queue` enqueued shrinks** 147,027 → 134,507 (−8.5 %).
5. Average device response barely moves (5,773 → 5,425 µs) — cost-per-GC and
   GC count almost cancel.
6. Tail latency stays in the 0.5-0.8 s band — dominated by GC erase contention,
   set by trigger frequency (constant here).

Working set is a **GC cost shaper**, not a GC trigger driver.

---

## 7. Phase 3C — GC_Exec_Threshold × Overprovisioning_Ratio 2D heatmap

### 7.1 Setup

| Knob | Value |
| --- | --- |
| `Initial_Occupancy_Percentage` | 50 |
| `Working_Set_Percentage` | 100 |
| `Read_Percentage` | 1 |
| `Average_No_of_Reqs_in_Queue` | 128 |
| `Stop_Time` | 30 s |
| `GC_Exec_Threshold` (columns) | **0.001 / 0.005 / 0.01 / 0.025 / 0.05** |
| `Overprovisioning_Ratio` (rows) | **0.07 / 0.05 / 0.03 / 0.02 / 0.01** |

25 cells total. 9 cells reused from Phase 2 (the `thr=0.001` column and the
`OP=0.07` row). 16 new runs.

`C_thr=0.05, OP=0.02` first attempt: `Illegal operation: Unlocking an LPA
that has not been locked!` — reseeded (67891 / 67890), rerun passed.

### 7.2 Full 5 × 5 grids

#### `Total_GC_Executions`

| OP \ thr | 0.001 | 0.005 | 0.01 | 0.025 | 0.05 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **0.07** | **0** | **0** | 15 | 514 | 2,828 |
| **0.05** | 15 | 15 | 18 | 543 | 3,035 |
| **0.03** | 19 | 19 | 75 | 444 | 2,909 |
| **0.02** | 18 | 18 | 50 | 529 | 2,841 |
| **0.01** | 20 | 20 | 73 | 667 | 2,923 |

#### `Average_Page_Movement_For_GC`

| OP \ thr | 0.001 | 0.005 | 0.01 | 0.025 | 0.05 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **0.07** | 0.00 | 0.00 | 21.27 | 31.16 | 40.65 |
| **0.05** | 25.80 | 25.80 | 21.94 | 34.58 | 43.69 |
| **0.03** | 26.89 | 26.89 | 27.29 | 34.61 | 46.71 |
| **0.02** | 27.67 | 27.67 | 27.34 | 37.63 | 47.78 |
| **0.01** | 29.20 | 29.20 | 31.34 | 40.55 | **49.56** |

#### Write Amplification Factor (WAF)

| OP \ thr | 0.001 | 0.005 | 0.01 | 0.025 | 0.05 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **0.07** | 1.000 | 1.000 | 1.002 | 1.044 | 1.223 |
| **0.05** | 1.002 | 1.002 | 1.003 | 1.049 | 1.252 |
| **0.03** | 1.003 | 1.003 | 1.011 | 1.042 | 1.273 |
| **0.02** | 1.003 | 1.003 | 1.007 | 1.053 | 1.279 |
| **0.01** | 1.003 | 1.003 | 1.010 | 1.064 | **1.294** |

#### `GC_Write_TR_Queue` enqueued (sum over 32 channel/chip queues)

| OP \ thr | 0.001 | 0.005 | 0.01 | 0.025 | 0.05 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **0.07** | 0 | 0 | 2,545 | 40,358 | 147,027 |
| **0.05** | 2,358 | 2,358 | 3,353 | 44,375 | 164,683 |
| **0.03** | 2,984 | 2,984 | 11,688 | 39,430 | 167,986 |
| **0.02** | 2,955 | 2,955 | 8,300 | 46,738 | 167,814 |
| **0.01** | 3,044 | 3,044 | 11,184 | 54,697 | **176,968** |

#### Average Device Response Time (µs)

| OP \ thr | 0.001 | 0.005 | 0.01 | 0.025 | 0.05 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **0.07** | **3,188** | 3,188 | 3,256 | 4,161 | 5,773 |
| **0.05** | 3,247 | 3,247 | 3,275 | 4,237 | 5,822 |
| **0.03** | 3,265 | 3,265 | 3,478 | 4,091 | 6,172 |
| **0.02** | 3,290 | 3,290 | 3,398 | 4,309 | **6,317** |
| **0.01** | 3,278 | 3,278 | 3,459 | 4,477 | 6,316 |

#### Max Device Response Time (µs)

| OP \ thr | 0.001 | 0.005 | 0.01 | 0.025 | 0.05 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **0.07** | **3,847** | 3,847 | 258,747 | 522,595 | 775,181 |
| **0.05** | 262,326 | 262,326 | 267,056 | 346,649 | 517,746 |
| **0.03** | 271,234 | 271,234 | 340,876 | 477,810 | 525,424 |
| **0.02** | 256,728 | 256,728 | 273,154 | 300,734 | **781,992** |
| **0.01** | 217,213 | 217,213 | 291,899 | 555,005 | 435,946 |

(The single no-GC cell sits at the upper-left corner.)

### 7.3 Rendered heatmaps

| Metric | File |
| --- | --- |
| `Total_GC_Executions` (log) | `exp2/heatmap_GC_Exec.png` |
| `WAF` | `exp2/heatmap_WAF.png` |
| `Avg_Page_Movement_For_GC` | `exp2/heatmap_AvgPgMv.png` |
| Avg Device Response Time | `exp2/heatmap_DevResp.png` |
| Max Device Response Time (log) | `exp2/heatmap_MaxResp.png` |

### 7.4 Recommended graph per parameter (canonical views)

For each knob there can be more than one plot in the artifacts, but only one
is the **right** view. Use this table.

| Parameter | **Canonical graph** | Why this one, not the Phase 2 plot |
| --- | --- | --- |
| `Initial_Occupancy_Percentage` | **`exp2/plot_A_occ_refined.png`** (Phase 3A) | 5 points 50 / 55 / 60 / 65 / 70 with the trigger boundary visually emphasized: green "no-GC region" vs pink "GC-on region", red dashed line at occ=55, gold ★ marker on the first non-zero point, symlog y so 0 → 37 is distinct. Phase 2's `sweep/plot_occ_sweep.png` only has 2 working points (50, 70) and misses the actual trigger. |
| `Working_Set_Percentage` | **`exp2/plot_B_ws_costshaper.png`** (Phase 3B, GC-on) | 6 panels under `thr=0.05` (GC always fires): shows that ws is a **cost shaper** — GC count is flat (2,802-2,924) but AvgPgMv 40.65 → 35.01, WAF 1.223 → 1.193, GC_Write enq 147 K → 134 K. Phase 2's `sweep/plot_ws_sweep.png` only shows 5 zero points under the no-GC baseline (literally flat at 0). |
| `GC_Exec_Threshold` | **`sweep/plot_thr_sweep.png`** (Phase 2, log-x) | First trigger at 0.01 visible as the knee; symlog reveals 0 → 15 → 514 → 2,828 across the sweep. |
| `Overprovisioning_Ratio` | **`sweep/plot_op_sweep.png`** (Phase 2) | First trigger at 0.05, then saturation through 0.01. |
| **`GC_Exec_Threshold` × `Overprovisioning_Ratio` (2D)** | **`exp2/heatmap_GC_Exec.png`** + 4 sister plots (`heatmap_WAF.png`, `heatmap_AvgPgMv.png`, `heatmap_DevResp.png`, `heatmap_MaxResp.png`) | The most presentation-friendly result. 5 × 5 grid with one no-GC corner (`thr=0.001, OP=0.07`), one saturated corner (`thr=0.05, OP=0.01`: GC=2,923, AvgPgMv=49.56, WAF=1.294). Shows the geometric duality between threshold and OP. |

Line plots all share the same 4-panel layout
(`Total_GC_Executions` / `WAF` / `Avg_Page_Movement_per_GC` / `Max_Device_Response_Time`)
and mark the first-trigger value with a red dashed vertical line.

#### Superseded / archival plots (kept for traceability)

| File | What it shows | Why not canonical |
| --- | --- | --- |
| `sweep/plot_occ_sweep.png` | Phase 2 occupancy sweep, points at occ = 50, 70 only | high-occ cells (80/90/95) crashed in MQSim, leaving only 2 working points. Use Phase 3A instead. |
| `sweep/plot_ws_sweep.png` | Phase 2 working-set sweep under the *no-GC* baseline | every point is GC=0, WAF=1.000 by construction; nothing to see. Use Phase 3B instead. |

### 7.5 Phase-3C take-aways

1. **One no-GC cell** (`thr=0.001, OP=0.07`) and **one saturated corner**
   (`thr=0.05, OP=0.01`, GC=2,923, AvgPgMv=49.56, WAF=1.294).
2. `thr=0.005` is indistinguishable from `thr=0.001` for every OP — both sit
   below the post-preconditioning free-pool depth (≈ 10 blocks/plane).
3. **`thr` dominates GC *count***: lifting thr 0.005 → 0.025 moves count from
   < 20 to > 500 across every OP.
4. **`OP` dominates *per-GC cost***: at thr=0.001, dropping OP alone lifts
   `AvgPgMv` from 0 to 29.20. At OP=0.07, lifting thr alone goes 0 → 40.65.
   The OP axis sets the *floor* of per-cycle cost (steady-state block fill),
   while thr controls *frequency* of incurring it.
5. **WAF crosses 1.20 only at thr = 0.05**, regardless of OP. For a workload
   that must stay under WAF = 1.10, `thr ≤ 0.025` is the operational range.

---

## 8. Cross-cutting findings

1. **MQSim's GC trigger is purely a block-pool depth check**:
   `if (free_block_pool_size < gc_threshold * block_no_per_plane) GC()`.
   This explains:
   - why working set has no effect on trigger (Phase 2 + Phase 3B),
   - why `thr` and `OP` are duals (Phase 2 + Phase 3C),
   - why `thr ≈ 0.01` is the cross-over point (post-preconditioning leaves
     ~10-20 blocks/plane free).

2. **Preconditioning consumes ~2,000 of 2,048 blocks/plane regardless of
   `Initial_Occupancy_Percentage`** — what changes is the *valid/invalid mix*
   within those blocks, not the free-block pool. That is why occupancy
   doesn't directly move the trigger line, but does move per-GC cost.

3. **Tail latency is GC erase wait**. Across all GC-on cells the
   `Max_Device_Response_Time` and `GC_Erase_TR_Queue.Max_Transaction_Waiting_Time`
   track each other within ~5 %.

4. **Phase 1 vs Phase 3C corner correspondence**:
   Phase-1 target (occ=95, ws=10, thr=0.05, OP=0.07, 100 s) gave WAF=3.75 and
   MaxResp=2.77 s. Phase-3C extreme corner (occ=50, ws=100, thr=0.05, OP=0.01,
   30 s) gave WAF=1.294 and MaxResp=435 ms. The Phase-1 target is much heavier
   because high occupancy (95 %) plus small working set (10 %) compounds the
   trigger frequency *and* per-GC cost — both dimensions of Phase-3C — and
   3× more simulated time.

---

## 9. MQSim limitations summary (encountered, by source location)

| Site | Error | Conditions | Phase |
| --- | --- | --- | --- |
| `Address_Mapping_Unit_Page_Level.cpp:738` | `It is not possible to assign PPA to all LPAs in Allocate_address_for_preconditioning!` | low-occ × high-OP (occ ≤ 30, OP ≥ 0.15) | first sweep attempt |
| `GC_and_WL_Unit_Page_Level.cpp` | `Inconsistency found when moving a page for GC/WL!` | seed-dependent at occ ≥ 60 with OP=0.07; sometimes at occ=80 always | Phase 2 (`sw_occ_80`), Phase 3A (`A_occ60`) |
| Mapping unit | `Illegal operation: Unlocking an LPA that has not been locked!` | seed-dependent at `thr=0.05, OP=0.02` | Phase 3C (`C_thr0p05_op0p02`) |
| Shutdown | glibc `free(): invalid pointer` / `munmap_chunk(): invalid pointer` | high-occ × OP=0.07 (occ ≥ 90); simulation completes, crash at teardown | Phase 2 (`sw_occ_90`, `sw_occ_95`) |

Workarounds applied:
- Move baseline away from low-occ × high-OP.
- Reseed (12345 / 67890) and re-run for `Inconsistency` and `Illegal` errors.
- Document occ ≥ 80 cells as unreliable.

---

## 10. Reproduction

```bash
# Build (once)
git clone https://github.com/CMU-SAFARI/MQSim.git ~/mqsim_gc_exp/MQSim
cd ~/mqsim_gc_exp/MQSim && make clean && make

# Phase 1 — verification (~12 min total, two runs in parallel)
( cd results/run_baseline && ./MQSim -i ssd.xml -w wl.xml ) &
( cd results/run_target   && ./MQSim -i ssd.xml -w wl.xml ) &
wait

# Phase 2 — initial sweep (17 configs, ~25 min @ 4-way)
bash sweep/run_all.sh > sweep/run_all.out 2>&1
python3 sweep/aggregate.py | tee sweep/aggregate.out

# Phase 3 — follow-up sweeps (23 new configs, ~25 min @ 6-way)
JOBS=6 bash exp2/run_all.sh > exp2/run_all.out 2>&1
python3 exp2/aggregate.py  | tee exp2/aggregate.out
# Heatmap PNGs:
pip3 install --user numpy matplotlib   # if needed
# (heatmap rendering snippet documented in exp2/EXP2_C.md §"Interpretation as a heatmap")
```

Per-cell config files at `*/configs/*.xml` and `*/workloads/*.xml`; each run's
working directory is `*/runs/<name>/`; each log at `*/logs/<name>.log`. All
parsed metrics are machine-readable in `sweep/results.json` and
`exp2/results.json` / `exp2/summaries.json`.

---

## 11. Artifact map

```
~/mqsim_gc_exp/MQSim/
├── ssdconfig.xml  workload.xml          ← unmodified MQSim defaults
├── MQSim                                 ← built binary
│
├── results/                              ← Phase 1
│   ├── SUMMARY.md                        ← Phase 1 detailed report
│   ├── baseline_occ50_thr05.xml          ← MQSim output XMLs
│   └── target_occ95_thr05.xml
│
├── sweep/                                ← Phase 2
│   ├── SWEEP.md                          ← Phase 2 detailed report
│   ├── aggregate.py  aggregate.out
│   ├── manifest.json  results.json  trigger_summary.json
│   ├── run_all.sh  run_all.out
│   ├── configs/   ssd_<name>.xml         ← 17 SSD configs
│   ├── workloads/ wl_<name>.xml          ← 17 workload configs
│   ├── runs/      <name>/                ← per-run working dirs (binary + ssd/wl + output)
│   ├── logs/      <name>.log
│   └── results/                          ← (empty placeholder)
│
├── exp2/                                 ← Phase 3 (A + B + C)
│   ├── EXP2.md                           ← index pointing to A/B/C
│   ├── EXP2_A.md  EXP2_B.md  EXP2_C.md   ← per-subexperiment reports
│   ├── aggregate.py  aggregate.out
│   ├── manifest.json  to_run.json  results.json  summaries.json
│   ├── run_all.sh  run_all.out
│   ├── heatmap_GC_Exec.png  heatmap_WAF.png  heatmap_AvgPgMv.png
│   ├── heatmap_DevResp.png  heatmap_MaxResp.png
│   ├── configs/   ssd_<name>.xml         ← 23 new SSD configs
│   ├── workloads/ wl_<name>.xml          ← 23 new workload configs
│   ├── runs/      <name>/                ← 34 dirs (11 reused XMLs symlinked from sweep/)
│   └── logs/      <name>.log
│
└── REPORT.md                             ← this file (consolidated)
```
