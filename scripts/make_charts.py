"""Charts for the lab note. Numbers are the log-verified counts for batches 20261101-170501 (no defenses)
and 20261101-180853 (five defenses)."""
from pathlib import Path

import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent.parent / "site" / "assets"
INK, MUTED, GRID, ACCENT, GRAY = "#16171b", "#5f636e", "#e1e0d9", "#e34948", "#9aa0ad"
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 15, "text.color": INK, "axes.edgecolor": GRID,
                     "xtick.color": MUTED, "ytick.color": INK, "svg.fonttype": "none"})


def title(fig, main, sub):
    fig.text(0.04, 0.95, main, fontsize=23, fontweight="bold", va="top")
    fig.text(0.04, 0.865, sub, fontsize=15, color=MUTED, va="top")


def bars(ax, labels, values, colors, maximum, suffix=""):
    y = range(len(labels))[::-1]
    ax.barh(list(y), values, color=colors, height=0.56)
    ax.set_yticks(list(y), labels)
    ax.set_xlim(0, maximum)
    ax.tick_params(length=0)
    ax.xaxis.set_visible(False)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)
    for pos, v in zip(y, values):
        ax.text(v + maximum * 0.015, pos, f"{v}{suffix}", va="center", fontweight="bold")


# Chart 1: the trap followed the review being opened
fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.4), sharey=True)
fig.subplots_adjust(left=0.31, right=0.97, top=0.66, bottom=0.12, wspace=0.08)
title(fig, "Once the review was opened, the bot repeated the code", "10 campaigns per group. It happened every time it was opened: 7 of 7, then 6 of 6 with defenses on.")
labels = ["Closer opened the review,\nwithout shared notes", "Closer opened the review,\nwith shared notes", "Bot repeated the code"]
for ax, name, data in ((axes[0], "No defenses", [0, 7, 7]), (axes[1], "Five defenses on", [0, 6, 6])):
    bars(ax, labels, data, [GRAY, GRAY, ACCENT], 10, " of 10")
    ax.set_title(name, loc="left", fontsize=16, fontweight="bold", pad=12)
fig.text(0.04, 0.035, "One model, one fake shop, small sample. The pattern was spotted after the runs.", color=MUTED, fontsize=13)
fig.savefig(OUT / "trap-by-review-opened.png", dpi=150)
fig.savefig(OUT / "trap-by-review-opened.svg")

# Chart 2: what the output guard's 63 blocks contained
fig, ax = plt.subplots(figsize=(12.8, 6.4))
fig.subplots_adjust(left=0.31, right=0.95, top=0.68, bottom=0.14)
title(fig, "The output guard mostly blocked customer data, not the code", "What the 63 blocked replies contained, out of 152 checked (five defenses on).")
bars(ax, ["Another customer's\nname or address", "The planted code", "None of these found", "The shop's refund secret"],
     [56, 3, 3, 1], [GRAY, ACCENT, GRAY, GRAY], 62)
fig.text(0.04, 0.035, "Rough text match that doesn't exclude names the chatter typed first. Code: 1 closer draft, 2 staff bot drafts.", color=MUTED, fontsize=13)
fig.savefig(OUT / "output-guard-blocks.png", dpi=150)
fig.savefig(OUT / "output-guard-blocks.svg")
