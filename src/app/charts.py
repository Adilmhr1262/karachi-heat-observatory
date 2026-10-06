"""Matplotlib charts in the observatory's editorial style.

All charts are drawn from the versioned grid parquet or the analysis
summary; nothing is recomputed beyond display aggregation.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from styles import HEAT, INK, MUTED, PAPER, RULE, TEAL

plt.rcParams.update({
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "savefig.facecolor": PAPER,
    "text.color": INK,
    "axes.labelcolor": INK,
    "axes.edgecolor": RULE,
    "xtick.color": INK,
    "ytick.color": INK,
    "grid.color": RULE,
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def _finish(fig, ax):
    fig.tight_layout()
    return fig


def fig_correlation_timeseries(summary):
    corr = summary.get("correlation") or []
    if not corr:
        return None
    fig, ax = plt.subplots(figsize=(8, 3.6))
    yrs = [c["year"] for c in corr]
    pr = [c["pearson_r"] for c in corr]
    ax.errorbar(
        yrs, pr,
        yerr=[[c["pearson_r"] - c["pearson_ci"][0] for c in corr],
              [c["pearson_ci"][1] - c["pearson_r"] for c in corr]],
        fmt="o-", color=TEAL, ecolor=TEAL, capsize=3, label="Pearson r",
    )
    if all("spearman_rho" in c for c in corr):
        sr = [c["spearman_rho"] for c in corr]
        ax.errorbar(
            yrs, sr,
            yerr=[[c["spearman_rho"] - c["spearman_ci"][0] for c in corr],
                  [c["spearman_ci"][1] - c["spearman_rho"] for c in corr]],
            fmt="s--", color=HEAT, ecolor=HEAT, capsize=3, label="Spearman rho",
        )
    ax.axhline(0, color=INK, linewidth=0.8)
    ax.set_xlabel("Hot season (year)")
    ax.set_ylabel("Correlation, NDVI vs LST")
    ax.legend(frameon=False)
    return _finish(fig, ax)


def fig_coverage(summary):
    cov = summary.get("coverage") or {}
    if not cov:
        return None
    yrs = sorted(int(y) for y in cov)
    vals = [float(cov[str(y)]) for y in yrs]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    bars = ax.bar([str(y) for y in yrs], vals, color=TEAL, edgecolor=INK, linewidth=0.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.015, f"{v:.0%}",
                ha="center", va="bottom", fontsize=8, color=INK)
    ax.set_ylim(0, 1.12)
    ax.set_xlabel("Hot season (year)")
    ax.set_ylabel("Share of land cells meeting the observation threshold")
    return _finish(fig, ax)


def fig_scene_counts(summary):
    sc = summary.get("scene_counts") or {}
    if not sc:
        return None
    yrs = sorted(int(y) for y in sc)
    vals = [int(sc[str(y)]) for y in yrs]
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.bar([str(y) for y in yrs], vals, color="#B9CFC2", edgecolor=INK, linewidth=0.5)
    ax.set_xlabel("Hot season (year)")
    ax.set_ylabel("Scenes used in the composite")
    return _finish(fig, ax)


def fig_scatter(df_year, year):
    if df_year is None or df_year.empty:
        return None
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    hb = ax.hexbin(df_year["ndvi"], df_year["lst_c"], gridsize=42,
                   cmap="YlOrRd", mincnt=1)
    ax.set_xlabel("NDVI (unitless)")
    ax.set_ylabel("LST (degrees C)")
    ax.set_title(f"NDVI vs LST per 1 km cell, hot season {year}")
    cb = fig.colorbar(hb, ax=ax)
    cb.set_label("cells")
    return _finish(fig, ax)


def fig_distributions(df_year, year):
    if df_year is None or df_year.empty:
        return None
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 3.4))
    a1.hist(df_year["ndvi"].dropna(), bins=40, color=TEAL, edgecolor=PAPER)
    a1.set_xlabel("NDVI (unitless)")
    a1.set_ylabel("Cells")
    a2.hist(df_year["lst_c"].dropna(), bins=40, color=HEAT, edgecolor=PAPER)
    a2.set_xlabel("LST (degrees C)")
    a2.set_ylabel("Cells")
    fig.suptitle(f"Distributions across grid cells, hot season {year}")
    return _finish(fig, (a1, a2))


def fig_persistence(summary):
    p = summary.get("persistence")
    if not p:
        return None
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    ax.bar(["Observed overlap", "Expected by chance"],
           [p["years_overlap_observed"], p["expected_chance"]],
           color=[HEAT, "#B9CFC2"], edgecolor=INK, linewidth=0.5)
    ax.set_ylabel("Cells")
    ax.set_title("Hot and low-vegetation cells recurring across years")
    return _finish(fig, ax)
