#!/usr/bin/env python3
"""Parse 17 sweep outputs, build per-parameter trigger tables, dump JSON + Markdown."""
import xml.etree.ElementTree as ET, json, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAN = json.load(open(ROOT/"manifest.json"))
KINDS = ("User_Read_TR_Queue","User_Write_TR_Queue",
         "Mapping_Read_TR_Queue","Mapping_Write_TR_Queue",
         "GC_Read_TR_Queue","GC_Write_TR_Queue","GC_Erase_TR_Queue")

def parse(name):
    out = ROOT/"runs"/name/"wl_scenario_1.xml"
    log = ROOT/"logs"/f"{name}.log"
    if not out.exists():
        return {"name": name, "ok": False, "reason": "no output XML"}
    ftl = {}; flow = {}; sums = {k: dict(enq=0,deq=0,maxQ=0,maxW=0) for k in KINDS}
    crashed = False
    if log.exists():
        s = log.read_text()
        if "ERROR" in s or "invalid pointer" in s or "munmap_chunk" in s or "Inconsistency" in s:
            crashed = True
    root = ET.parse(out).getroot()
    for e in root.iter():
        if e.tag.endswith(".FTL"):
            ftl.update(e.attrib)
        if e.tag == "Host.IO_Flow":
            for c in e: flow[c.tag] = c.text
        for k in KINDS:
            if k in e.tag and "No_Of_Transactions_Enqueued" in e.attrib:
                d = sums[k]
                d["enq"] += int(e.attrib["No_Of_Transactions_Enqueued"])
                d["deq"] += int(e.attrib["No_Of_Transactions_Dequeued"])
                d["maxQ"] = max(d["maxQ"], int(e.attrib["Max_Queue_Length"]))
                d["maxW"] = max(d["maxW"], int(e.attrib["Max_Transaction_Waiting_Time"]))
                break
    uw = sums["User_Write_TR_Queue"]["enq"]
    gw = sums["GC_Write_TR_Queue"]["enq"]
    avg_pm = float(ftl.get("Average_Page_Movement_For_GC","0") or 0)
    # -nan when no GC happened
    if avg_pm != avg_pm: avg_pm = 0.0
    return {
        "name": name, "ok": True, "crashed": crashed,
        "Total_GC_Executions": int(ftl.get("Total_GC_Executions","0")),
        "Avg_Pg_Move_per_GC": avg_pm,
        "Issued_Erase_CMD": int(ftl.get("Issued_Flash_Erase_CMD","0")),
        "Issued_Prog_CMD": int(ftl.get("Issued_Flash_Program_CMD","0")),
        "GC_Read_Enq": sums["GC_Read_TR_Queue"]["enq"],
        "GC_Write_Enq": sums["GC_Write_TR_Queue"]["enq"],
        "GC_Erase_Enq": sums["GC_Erase_TR_Queue"]["enq"],
        "Max_GC_Erase_Wait_us": sums["GC_Erase_TR_Queue"]["maxW"],
        "User_Writes": uw,
        "User_Reads": sums["User_Read_TR_Queue"]["enq"],
        "WAF": (uw+gw)/uw if uw else None,
        "Device_Resp_us": int(flow.get("Device_Response_Time","0") or 0),
        "Max_Device_Resp_us": int(flow.get("Max_Device_Response_Time","0") or 0),
        "Host_Req_Count": int(flow.get("Request_Count","0") or 0),
    }

results = {n: parse(n) for n in MAN}
json.dump(results, open(ROOT/"results.json","w"), indent=2)

# ===== Per-run summary =====
print("\n" + "="*110)
print("PER-RUN SUMMARY  (baseline = occ=50, ws=100, thr=0.001, OP=0.07, Read%=1, QD=128, Stop=30s)")
print("="*110)
hdr = f"{'name':<18}{'occ':>5}{'ws':>5}{'thr':>8}{'OP':>6}{'GC_Exec':>9}{'AvgPgMv':>9}{'GC_Erase_Enq':>14}{'UserW':>9}{'WAF':>6}{'DevResp':>10}{'MaxResp':>10}{'OK?':>10}"
print(hdr)
for n, r in results.items():
    m = MAN[n]
    if not r.get("ok"):
        print(f"{n:<18}{m['occ']:>5}{m['ws']:>5}{m['thr']:>8}{m['op']:>6}  [NO OUTPUT — {r.get('reason','?')}]")
        continue
    ok = "CRASH" if r.get("crashed") else "ok"
    waf = f"{r['WAF']:.2f}" if r.get('WAF') else "-"
    print(f"{n:<18}{m['occ']:>5}{m['ws']:>5}{m['thr']:>8}{m['op']:>6}{r['Total_GC_Executions']:>9}{r['Avg_Pg_Move_per_GC']:>9.1f}{r['GC_Erase_Enq']:>14}{r['User_Writes']:>9}{waf:>6}{r['Device_Resp_us']:>10}{r['Max_Device_Resp_us']:>10}{ok:>10}")

# ===== Per-parameter trigger map =====
SWEEPS = {
    "Initial_Occupancy_Percentage": ("occ", [50, 70, 80, 90, 95]),
    "Working_Set_Percentage":       ("ws",  [100, 50, 20, 10, 5]),
    "GC_Exec_Threshold":            ("thr", [0.001, 0.005, 0.01, 0.025, 0.05]),
    "Overprovisioning_Ratio":       ("op",  [0.07, 0.05, 0.03, 0.02, 0.01]),
}

def find_name(param, val):
    BASE = {"occ":50,"ws":100,"thr":0.001,"op":0.07}
    if val == BASE[param]: return "baseline"
    if param == "occ": return f"sw_occ_{val}"
    if param == "ws":  return f"sw_ws_{val}"
    if param == "thr": return "sw_thr_" + str(val).replace(".","p")
    if param == "op":  return "sw_op_"  + str(val).replace(".","p")

print("\n" + "="*110)
print("PER-PARAMETER GC TRIGGER MAP")
print("="*110)
trigger_summary = {}
for fullname, (param, vals) in SWEEPS.items():
    print(f"\n[{fullname}]  others held at baseline (occ=50, ws=100, thr=0.001, OP=0.07)")
    print(f"  {'value':>10}{'GC_Exec':>10}{'AvgPgMv':>10}{'GC_Erase_Enq':>14}{'UserW':>10}{'WAF':>6}{'DevResp_us':>12}{'trigger?':>12}")
    first = None
    rows = []
    for v in vals:
        n = find_name(param, v)
        r = results.get(n)
        if r is None or not r["ok"]:
            print(f"  {v!s:>10}  [missing or NO OUTPUT]")
            rows.append({"value": v, "missing": True})
            continue
        if r.get("crashed") and r["User_Writes"] < 10000:
            tag = "[CRASH]"
        else:
            tg = r["Total_GC_Executions"] > 0
            tag = "YES" if tg else "no"
            if tg and first is None:
                first = v; tag = "**FIRST**"
        waf = f"{r['WAF']:.2f}" if r.get('WAF') else "-"
        print(f"  {v!s:>10}{r['Total_GC_Executions']:>10}{r['Avg_Pg_Move_per_GC']:>10.1f}{r['GC_Erase_Enq']:>14}{r['User_Writes']:>10}{waf:>6}{r['Device_Resp_us']:>12}{tag:>12}")
        rows.append({"value": v, "name": n, **r})
    trigger_summary[fullname] = {"param_short": param, "first_trigger": first, "rows": rows}
    if first is not None:
        print(f"  -> GC starts triggering at {param}={first}")
    else:
        print(f"  -> no GC across entire sweep range (within tested values)")

json.dump(trigger_summary, open(ROOT/"trigger_summary.json","w"), indent=2)
