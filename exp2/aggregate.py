#!/usr/bin/env python3
"""Aggregate exp2 results into per-experiment summaries + 2D heatmap data."""
import xml.etree.ElementTree as ET, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAN  = json.load(open(ROOT/"manifest.json"))
KINDS = ("User_Read_TR_Queue","User_Write_TR_Queue",
         "GC_Read_TR_Queue","GC_Write_TR_Queue","GC_Erase_TR_Queue")

def parse(name):
    out = ROOT/"runs"/name/"wl_scenario_1.xml"
    log = ROOT/"logs"/f"{name}.log"
    if not out.exists():
        return {"name": name, "ok": False, "reason": "no XML"}
    ftl={}; flow={}; sums={k: dict(enq=0,deq=0,maxQ=0,maxW=0) for k in KINDS}
    crashed=False
    if log.exists():
        s = log.read_text()
        if "ERROR" in s or "invalid pointer" in s or "Inconsistency" in s or "Illegal" in s:
            crashed=True
    root = ET.parse(out).getroot()
    for e in root.iter():
        if e.tag.endswith(".FTL"): ftl.update(e.attrib)
        if e.tag == "Host.IO_Flow":
            for c in e: flow[c.tag] = c.text
        for k in KINDS:
            if k in e.tag and "No_Of_Transactions_Enqueued" in e.attrib:
                d=sums[k]
                d["enq"] += int(e.attrib["No_Of_Transactions_Enqueued"])
                d["deq"] += int(e.attrib["No_Of_Transactions_Dequeued"])
                d["maxQ"] = max(d["maxQ"], int(e.attrib["Max_Queue_Length"]))
                d["maxW"] = max(d["maxW"], int(e.attrib["Max_Transaction_Waiting_Time"]))
                break
    uw=sums["User_Write_TR_Queue"]["enq"]; gw=sums["GC_Write_TR_Queue"]["enq"]
    avg_pm = float(ftl.get("Average_Page_Movement_For_GC","0") or 0)
    if avg_pm != avg_pm: avg_pm = 0.0
    return {
        "name": name, "ok": True, "crashed": crashed,
        "GC_Exec": int(ftl.get("Total_GC_Executions","0")),
        "AvgPgMv": avg_pm,
        "GC_Read_Enq": sums["GC_Read_TR_Queue"]["enq"],
        "GC_Write_Enq": sums["GC_Write_TR_Queue"]["enq"],
        "GC_Erase_Enq": sums["GC_Erase_TR_Queue"]["enq"],
        "GC_Erase_MaxWait_us": sums["GC_Erase_TR_Queue"]["maxW"],
        "GC_Write_MaxWait_us": sums["GC_Write_TR_Queue"]["maxW"],
        "UserW": uw, "UserR": sums["User_Read_TR_Queue"]["enq"],
        "WAF": (uw+gw)/uw if uw else None,
        "DevResp_us": int(flow.get("Device_Response_Time","0") or 0),
        "MaxDevResp_us": int(flow.get("Max_Device_Response_Time","0") or 0),
        "Host_Req_Count": int(flow.get("Request_Count","0") or 0),
    }

results = {n: parse(n) for n in MAN}
json.dump(results, open(ROOT/"results.json","w"), indent=2)

def fmt_run(r):
    if not r.get("ok"): return "[NO XML]"
    return ""

# ======================== EXP A ========================
print("="*120)
print("EXPERIMENT A — Initial_Occupancy_Percentage trigger boundary refinement")
print("  base: ws=100, thr=0.001, OP=0.07, Read%=1, QD=128, Stop=30s")
print("="*120)
print(f"  {'occ':>5}{'GC_Exec':>10}{'AvgPgMv':>10}{'GC_Erase_Enq':>14}{'GC_Write_Enq':>14}{'UserW':>10}{'WAF':>7}{'DevResp_us':>12}{'MaxResp_us':>12}{'status':>10}")
A_rows = []
for n in [n for n in MAN if MAN[n]["exp"]=="A"]:
    m = MAN[n]; r = results[n]
    if not r.get("ok"):
        print(f"  {m['occ']:>5}  [NO OUTPUT]"); continue
    waf = f"{r['WAF']:.3f}" if r.get('WAF') else "-"
    st = "CRASH" if r["crashed"] else "ok"
    print(f"  {m['occ']:>5}{r['GC_Exec']:>10}{r['AvgPgMv']:>10.2f}{r['GC_Erase_Enq']:>14}{r['GC_Write_Enq']:>14}{r['UserW']:>10}{waf:>7}{r['DevResp_us']:>12}{r['MaxDevResp_us']:>12}{st:>10}")
    A_rows.append({"occ": m["occ"], **r})
# Find first trigger
A_rows.sort(key=lambda x: x["occ"])
first = next((row["occ"] for row in A_rows if row["GC_Exec"] > 0), None)
print(f"\n  -> First GC trigger at occ = {first}")

# ======================== EXP B ========================
print("\n"+"="*120)
print("EXPERIMENT B — Working set as GC-COST shaping (not trigger)")
print("  base: occ=50, thr=0.05, OP=0.07, Read%=1, QD=128, Stop=30s   (GC always fires)")
print("="*120)
print(f"  {'ws':>5}{'GC_Exec':>10}{'AvgPgMv':>10}{'WAF':>7}{'GC_Write_Enq':>14}{'GC_Erase_MaxW_us':>18}{'DevResp_us':>12}{'MaxResp_us':>12}{'status':>10}")
B_rows=[]
for n in [n for n in MAN if MAN[n]["exp"]=="B"]:
    m = MAN[n]; r = results[n]
    if not r.get("ok"):
        print(f"  {m['ws']:>5}  [NO OUTPUT]"); continue
    waf = f"{r['WAF']:.3f}" if r.get('WAF') else "-"
    st = "CRASH" if r["crashed"] else "ok"
    print(f"  {m['ws']:>5}{r['GC_Exec']:>10}{r['AvgPgMv']:>10.2f}{waf:>7}{r['GC_Write_Enq']:>14}{r['GC_Erase_MaxWait_us']:>18}{r['DevResp_us']:>12}{r['MaxDevResp_us']:>12}{st:>10}")
    B_rows.append({"ws": m["ws"], **r})
B_rows.sort(key=lambda x: -x["ws"])

# ======================== EXP C ========================
print("\n"+"="*120)
print("EXPERIMENT C — GC_Exec_Threshold × Overprovisioning_Ratio 2D matrix")
print("  base: occ=50, ws=100, Read%=1, QD=128, Stop=30s")
print("="*120)
THRS = [0.001, 0.005, 0.01, 0.025, 0.05]
OPS  = [0.07, 0.05, 0.03, 0.02, 0.01]

def cell_name(thr, op):
    return f"C_thr{str(thr).replace('.','p')}_op{str(op).replace('.','p')}"

# Heatmap helper: pick a metric and print as grid
def grid(metric, fmt, label):
    print(f"\n[{label}]  rows = OP (Overprovisioning), cols = thr (GC_Exec_Threshold)")
    hdr = f"  {'OP \\ thr':>10}" + "".join(f"{t:>12}" for t in THRS)
    print(hdr)
    for op in OPS:
        row = f"  {op:>10}"
        for thr in THRS:
            n = cell_name(thr, op)
            r = results.get(n)
            if not r or not r.get("ok"):
                row += f"{'NaN':>12}"
            else:
                val = r[metric]
                if val is None:
                    row += f"{'-':>12}"
                else:
                    row += f"{fmt.format(val):>12}"
        print(row)

grid("GC_Exec", "{:.0f}", "Total_GC_Executions")
grid("AvgPgMv", "{:.2f}", "Average_Page_Movement_For_GC")
grid("WAF",     "{:.3f}", "Write Amplification Factor (WAF)")
grid("GC_Write_Enq", "{:.0f}", "GC_Write_TR_Queue enqueued (sum 32 q)")
grid("DevResp_us", "{:.0f}", "Avg Device Response Time (us)")
grid("MaxDevResp_us", "{:.0f}", "Max Device Response Time (us)")

# Also detect crashes in the grid
print(f"\n[Status grid]")
print(f"  {'OP \\ thr':>10}" + "".join(f"{t:>12}" for t in THRS))
for op in OPS:
    row = f"  {op:>10}"
    for thr in THRS:
        n = cell_name(thr, op)
        r = results.get(n)
        if not r:           row += f"{'-':>12}"
        elif not r.get("ok"): row += f"{'NO XML':>12}"
        elif r.get("crashed"): row += f"{'CRASH':>12}"
        else:               row += f"{'ok':>12}"
    print(row)

# Dump per-experiment JSON
json.dump({"A_rows": A_rows, "B_rows": B_rows,
           "C_grid": [[results.get(cell_name(t,op),{}) for t in THRS] for op in OPS],
           "THRS": THRS, "OPS": OPS},
          open(ROOT/"summaries.json","w"), indent=2, default=str)
