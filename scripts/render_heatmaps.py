#!/usr/bin/env python3
"""Render Phase 3C 2D heatmaps for GC_Exec_Threshold × Overprovisioning_Ratio.

Outputs (in exp2/):
  heatmap_GC_Exec.png  heatmap_WAF.png  heatmap_AvgPgMv.png
  heatmap_DevResp.png  heatmap_MaxResp.png

Reads:
  exp2/summaries.json  (run exp2/aggregate.py first)
"""
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

d = json.load(open("exp2/summaries.json"))
thrs, ops = d["THRS"], d["OPS"]
grid = d["C_grid"]


def matrix(metric):
    return np.array(
        [[(row[i].get(metric, 0) or 0) for i in range(len(thrs))]
         for row in grid],
        dtype=float)


def plot(M, title, fname, transform=lambda x: x, cmap="viridis", fmt="{:.0f}"):
    fig, ax = plt.subplots(figsize=(7, 5))
    Mt = transform(M)
    im = ax.imshow(Mt, aspect="auto", cmap=cmap)
    ax.set_xticks(np.arange(len(thrs)))
    ax.set_yticks(np.arange(len(ops)))
    ax.set_xticklabels([str(t) for t in thrs])
    ax.set_yticklabels([str(o) for o in ops])
    ax.set_xlabel("GC_Exec_Threshold")
    ax.set_ylabel("Overprovisioning_Ratio")
    ax.set_title(title)
    vmin, vmax = Mt.min(), Mt.max()
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v, vt = M[i, j], Mt[i, j]
            color = "white" if (vt - vmin) > 0.5 * (vmax - vmin) else "black"
            ax.text(j, i, fmt.format(v), ha="center", va="center",
                    color=color, fontsize=9)
    plt.colorbar(im, ax=ax)
    plt.tight_layout()
    plt.savefig(f"exp2/{fname}", dpi=140)
    plt.close()
    print(f"wrote exp2/{fname}")


plot(matrix("GC_Exec"),       "Total_GC_Executions (log10 scale, +1)",
     "heatmap_GC_Exec.png",
     transform=lambda x: np.log10(1 + x), fmt="{:.0f}")
plot(matrix("WAF"),           "Write Amplification (WAF)",
     "heatmap_WAF.png",
     fmt="{:.2f}", cmap="magma")
plot(matrix("AvgPgMv"),       "Average page movement per GC",
     "heatmap_AvgPgMv.png",
     fmt="{:.1f}", cmap="plasma")
plot(matrix("DevResp_us"),    "Avg Device Response Time (us)",
     "heatmap_DevResp.png",
     fmt="{:.0f}", cmap="cividis")
plot(matrix("MaxDevResp_us"), "Max Device Response Time (us, log10)",
     "heatmap_MaxResp.png",
     transform=lambda x: np.log10(1 + x), fmt="{:.0f}", cmap="inferno")
