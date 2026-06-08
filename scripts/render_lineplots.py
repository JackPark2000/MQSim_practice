#!/usr/bin/env python3
"""Render Phase 2 sweep line plots + Phase 3A occupancy refinement plot.

Outputs:
  sweep/plot_occ_sweep.png   sweep/plot_ws_sweep.png
  sweep/plot_thr_sweep.png   sweep/plot_op_sweep.png
  exp2/plot_A_occ_refined.png
  exp2/plot_B_ws_costshaper.png

Reads:
  sweep/results.json (run aggregate.py first)
  exp2/results.json
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sweep_res = json.load(open("sweep/results.json"))
exp2_res  = json.load(open("exp2/results.json"))


def normalize(r):
    """Map sweep/results.json and exp2/results.json into one schema."""
    if not r or not r.get("ok"):
        return None
    return {
        "Total_GC_Executions": r.get("Total_GC_Executions", r.get("GC_Exec")),
        "Avg_Pg_Move_per_GC":  r.get("Avg_Pg_Move_per_GC",  r.get("AvgPgMv")),
        "WAF":                 r.get("WAF"),
        "Max_Device_Resp_us":  r.get("Max_Device_Resp_us",  r.get("MaxDevResp_us")),
        "Device_Resp_us":      r.get("Device_Resp_us",      r.get("DevResp_us")),
        "GC_Write_Enq":        r.get("GC_Write_Enq"),
        "GC_Erase_MaxWait_us": r.get("GC_Erase_MaxWait_us"),
    }


def collect_p2(param, values):
    BASE = {"occ": 50, "ws": 100, "thr": 0.001, "op": 0.07}
    rows = []
    for v in values:
        if v == BASE[param]:
            name = "baseline"
        else:
            tag = {"occ": "sw_occ_", "ws": "sw_ws_",
                   "thr": "sw_thr_", "op": "sw_op_"}[param]
            label = str(v).replace(".", "p") if param in ("thr", "op") else str(v)
            name = f"{tag}{label}"
        nr = normalize(sweep_res.get(name))
        if nr:
            rows.append({"v": v, **nr})
    return rows


def panel_plot(rows, x_label, fname, title, xlog=False, invert_x=False):
    """4-panel line plot with first-trigger marker."""
    xs = [r["v"] for r in rows]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    metrics = [
        ("Total_GC_Executions", "Total_GC_Executions",         "log"),
        ("WAF",                 "Write Amplification (WAF)",   "linear"),
        ("Avg_Pg_Move_per_GC",  "Avg page movement / GC",      "linear"),
        ("Max_Device_Resp_us",  "Max Device Resp Time (µs)",   "log"),
    ]
    first_trig_v = next(
        (r["v"] for r in rows if (r.get("Total_GC_Executions") or 0) > 0), None)
    for ax, (key, ylabel, yscale) in zip(axes.flat, metrics):
        ys = [(r.get(key) or 0) for r in rows]
        ys_plot = [max(y, 1) if yscale == "log" else y for y in ys]
        ax.plot(xs, ys_plot, "o-", linewidth=2, markersize=8)
        for x, y in zip(xs, ys):
            ax.annotate(
                f"{y:.3g}" if isinstance(y, float) else str(y),
                (x, max(y, 1) if yscale == "log" else y),
                textcoords="offset points", xytext=(5, 5), fontsize=8)
        ax.set_xlabel(x_label)
        ax.set_ylabel(ylabel)
        ax.set_title(ylabel)
        if yscale == "log":
            ax.set_yscale("log")
        if xlog:
            ax.set_xscale("log")
        if invert_x:
            ax.invert_xaxis()
        ax.grid(True, alpha=0.3)
        if first_trig_v is not None:
            ax.axvline(first_trig_v, color="red", linestyle="--",
                       linewidth=2, alpha=0.5,
                       label=f"first trigger: {x_label}={first_trig_v}")
            ax.legend(fontsize=8, loc="best")
    fig.suptitle(title, fontsize=13)
    plt.tight_layout()
    plt.savefig(fname, dpi=140)
    plt.close()
    print(f"wrote {fname}")


# === Phase 2 (4 single-parameter sweeps) ===
panel_plot(collect_p2("occ", [50, 70]),
           "Initial_Occupancy_Percentage", "sweep/plot_occ_sweep.png",
           "Phase 2 — Initial_Occupancy sweep (ws=100, thr=0.001, OP=0.07, 30s)\n"
           "[80/90/95 omitted: MQSim crashes]")
panel_plot(collect_p2("ws", [100, 50, 20, 10, 5]),
           "Working_Set_Percentage", "sweep/plot_ws_sweep.png",
           "Phase 2 — Working_Set sweep (occ=50, thr=0.001, OP=0.07, 30s) — NO TRIGGER",
           invert_x=True)
panel_plot(collect_p2("thr", [0.001, 0.005, 0.01, 0.025, 0.05]),
           "GC_Exec_Threshold", "sweep/plot_thr_sweep.png",
           "Phase 2 — GC_Exec_Threshold sweep (occ=50, ws=100, OP=0.07, 30s)",
           xlog=True)
panel_plot(collect_p2("op", [0.07, 0.05, 0.03, 0.02, 0.01]),
           "Overprovisioning_Ratio", "sweep/plot_op_sweep.png",
           "Phase 2 — Overprovisioning sweep (occ=50, ws=100, thr=0.001, 30s)",
           invert_x=True)


# === Phase 3A (refined occupancy plot with strong trigger=55 emphasis) ===
A_rows = []
for v in [50, 55, 60, 65, 70]:
    if v == 50:
        r = sweep_res["baseline"]
    elif v == 70:
        r = sweep_res["sw_occ_70"]
    else:
        r = exp2_res[f"A_occ{v}"]
    nr = normalize(r)
    nr["v"] = v
    A_rows.append(nr)

TRIGGER = 55
trig_row = next(r for r in A_rows if r["v"] == TRIGGER)
fig, axes = plt.subplots(2, 2, figsize=(13, 9))
fig.suptitle("Phase 3A — Initial_Occupancy_Percentage trigger boundary\n"
             "ws=100, thr=0.001, OP=0.07, Read%=1, QD=128, Stop=30s\n"
             f"GC first triggers at occ = {TRIGGER}",
             fontsize=13, fontweight="bold")
xs = [r["v"] for r in A_rows]
point_colors = ["#2ca02c" if (r["Total_GC_Executions"] or 0) == 0 else "#d62728"
                for r in A_rows]
panels = [
    ("Total_GC_Executions",  "Total_GC_Executions — 0 → 37 → 148 → 440 → 691",      "symlog", "{}", 10),
    ("WAF",                  "Write Amplification — 1.000 → 1.005 → 1.022 → 1.072 → 1.136", "linear", "{:.3f}", None),
    ("Avg_Pg_Move_per_GC",   "Per-GC cost — 0 → 31.6 → 48.1 → 65.2 → 84.4",         "linear", "{:.1f}", None),
    ("Max_Device_Resp_us",   "Tail latency — 3.8 ms → 521 ms → 821 ms → 823 ms → 760 ms", "log", "{:,}", None),
]
for ax, (key, title, yscale, fmt, linthresh) in zip(axes.flat, panels):
    ys = [r[key] for r in A_rows]
    ax.axvspan(48, TRIGGER, color="#d4edda", alpha=0.6, label="no-GC region")
    ax.axvspan(TRIGGER, 72, color="#f8d7da", alpha=0.4, label="GC-on region")
    ax.plot(xs, ys, "-", color="gray", linewidth=1.5, zorder=2)
    ax.scatter(xs, ys, c=point_colors, s=140, zorder=3,
               edgecolors="black", linewidth=1.2)
    for r in A_rows:
        v = r[key]
        s = fmt.format(v) if "{" in fmt else str(v)
        ax.annotate(s, (r["v"], v),
                    textcoords="offset points", xytext=(0, 12),
                    ha="center", fontsize=10, fontweight="bold")
    ax.scatter([TRIGGER], [trig_row[key]], marker="*", s=600,
               color="gold", edgecolors="black", zorder=4)
    ax.axvline(TRIGGER, color="red", linestyle="--", linewidth=2, alpha=0.7)
    if yscale == "symlog":
        ax.set_yscale("symlog", linthresh=linthresh)
    elif yscale == "log":
        ax.set_yscale("log")
    ax.set_xlim(48, 72)
    ax.set_xticks([50, 55, 60, 65, 70])
    ax.set_xlabel("Initial_Occupancy_Percentage", fontsize=11)
    ax.set_title(title, fontsize=11)
    ax.grid(True, alpha=0.3)

axes[0, 0].annotate(
    f"occ = {TRIGGER}\nGC_Exec = 37\n(jumps from 0)",
    xy=(TRIGGER, 37), xytext=(58, 5),
    fontsize=10, fontweight="bold", color="darkred",
    arrowprops=dict(arrowstyle="->", color="darkred", lw=1.5),
    bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff3cd",
              edgecolor="darkred"))
axes[0, 0].legend(loc="upper left", fontsize=9)
plt.tight_layout(rect=[0, 0, 1, 0.94])
plt.savefig("exp2/plot_A_occ_refined.png", dpi=140)
plt.close()
print("wrote exp2/plot_A_occ_refined.png")


# === Phase 3B (working-set under GC-on; 6 panels) ===
B_rows = []
for v in [100, 50, 20, 10, 5]:
    r = sweep_res["sw_thr_0p05"] if v == 100 else exp2_res[f"B_ws{v}"]
    nr = normalize(r)
    if nr:
        B_rows.append({"v": v, **nr})

fig, axes = plt.subplots(2, 3, figsize=(15, 8))
xs = [r["v"] for r in B_rows]
panels = [
    ("Total_GC_Executions",       "Total_GC_Executions (~flat)"),
    ("Avg_Pg_Move_per_GC",        "Avg page movement / GC"),
    ("WAF",                       "Write Amplification (WAF)"),
    ("GC_Write_Enq",              "GC_Write_TR_Queue enq (sum 32q)"),
    ("Device_Resp_us",            "Avg Device Resp (µs)"),
    ("Max_Device_Resp_us",        "Max Device Resp (µs)"),
]
for ax, (key, ylabel) in zip(axes.flat, panels):
    ys = [(r.get(key) or 0) for r in B_rows]
    ax.plot(xs, ys, "o-", linewidth=2, markersize=8, color="darkred")
    for x, y in zip(xs, ys):
        ax.annotate(f"{y:.3g}" if isinstance(y, float) else str(y),
                    (x, y), textcoords="offset points", xytext=(5, 5),
                    fontsize=8)
    ax.set_xlabel("Working_Set_Percentage")
    ax.set_ylabel(ylabel)
    ax.set_title(ylabel)
    ax.invert_xaxis()
    ax.grid(True, alpha=0.3)
fig.suptitle("Phase 3B — Working_Set under GC-on (thr=0.05, OP=0.07): "
             "trigger flat, cost shrinks", fontsize=13)
plt.tight_layout()
plt.savefig("exp2/plot_B_ws_costshaper.png", dpi=140)
plt.close()
print("wrote exp2/plot_B_ws_costshaper.png")
