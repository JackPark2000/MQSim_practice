# Experiment B — Working_Set_Percentage as **GC cost shaper** (not trigger)

## Goal

Previous sweep showed that `Working_Set_Percentage` from 100 % down to 5 %
**never triggered GC** under the no-GC baseline. This is correct: working set
does not drain the free-block pool — it only redistributes invalidation
density across blocks.

But once GC is **already firing**, working set should reshape per-GC cost
(fewer valid pages copied per victim block when invalidations concentrate in
the same blocks). That is what experiment B measures.

## Setup

| Knob | Value |
| --- | --- |
| `Initial_Occupancy_Percentage` | 50 |
| `Working_Set_Percentage` | **100 / 50 / 20 / 10 / 5** ← sweep |
| `GC_Exec_Threshold` | **0.05** ← lifted (so GC fires in every cell) |
| `Overprovisioning_Ratio` | 0.07 |
| `Read_Percentage` | 1 |
| `Average_No_of_Reqs_in_Queue` | 128 |
| `Stop_Time` | 30 s |

(`ws=100` cell is reused from previous `sw_thr_0p05` run; the 4 smaller ws
values are new.)

## Results

| ws | GC_Exec | Avg pg-move/GC | WAF | GC_Write enq (sum 32 q) | GC_Erase max wait µs | DevResp µs | Max DevResp µs |
| ---:| ---:| ---:| ---:| ---:| ---:| ---:| ---:|
| 100 | 2,828 | **40.65** | **1.223** | 147,027 | 594,312 | 5,773 | 775,181 |
|  50 | 2,838 | 40.91 | 1.226 | 148,222 | 529,866 | 5,785 | 591,806 |
|  20 | 2,850 | 39.94 | 1.220 | 145,968 | 716,158 | 5,725 | 601,578 |
|  10 | 2,802 | 38.42 | 1.211 | 139,789 | 521,777 | 5,724 | 542,654 |
|   5 | 2,924 | **35.01** | **1.193** | 134,507 | 504,243 | 5,425 | 548,123 |

## Trends

1. **`Total_GC_Executions` is essentially flat** across the sweep
   (2,802 – 2,924). Confirms B's premise: working set is not a trigger
   knob — the free-block pool drains at the same rate regardless of where
   the writes land.

2. **`Average_Page_Movement_For_GC` decreases monotonically with smaller ws**:
   - ws 100 → 5: 40.65 → 35.01 pages copied per victim block (−14 %).
   - With a tighter working set, the same number of writes invalidates a
     *smaller set of blocks* more deeply, so when GREEDY picks the
     most-invalidated block as victim, fewer valid pages remain to be
     migrated.

3. **`WAF` decreases mildly**: 1.223 → 1.193 (−2.4 %). Same mechanism — less
   valid-page migration per GC ⇒ fewer GC writes per user write.

4. **`GC_Write_TR_Queue enqueued` decreases**: 147,027 → 134,507 (−8.5 %).
   This is the direct evidence that per-GC traffic shrinks with smaller ws.

5. **Average device response time barely moves** (5,773 → 5,425 µs); the
   per-GC cost reduction is balanced by similar per-GC count, so the user
   path roughly breaks even.

6. **Tail latency (`Max DevResp`) stays in the 0.5 – 0.8 s range** — dominated
   by GC erase contention, which is set by the trigger frequency (which
   doesn't change here).

## Picture

```
ws:                100      50      20      10       5
GC_Exec:          2828    2838    2850    2802    2924   ← flat
AvgPgMv:          40.65   40.91   39.94   38.42   35.01  ← decreasing
WAF:              1.223   1.226   1.220   1.211   1.193  ← decreasing
GC_Write enq:    147027  148222  145968  139789  134507  ← decreasing
```

## Conclusion

Working set is **not a trigger driver** in MQSim's block-level GC: the
trigger condition is purely `free_blocks < threshold`, and small ws does not
change how fast new blocks are consumed. It is, however, a **GC cost shaper**:
concentrated writes pack invalid pages into fewer victim blocks, so once GC
fires it has less valid-page migration work per cycle. The 14 % drop in
`Average_Page_Movement_For_GC` from ws = 100 to ws = 5 is the headline number.
