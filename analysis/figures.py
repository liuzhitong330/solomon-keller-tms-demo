"""Three prespecified, participant-level figures; no selected 'best' examples."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TEAL = "#1f7a8c"


def make_figures(payload, destination):
    destination = Path(destination)
    destination.mkdir(exist_ok=True, parents=True)
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
        "axes.spines.right": False, "axes.edgecolor": "#aaaaaa", "text.color": "#222222",
        "axes.labelcolor": "#333333", "xtick.color": "#555555", "ytick.color": "#555555",
        "svg.hashsalt": "solomon-keller-tms-reanalysis-v1", "svg.fonttype": "none",
    })
    participants, budgets = payload["participants"], payload["meta"]["budgets"]
    rows = [p["readouts"]["C3"]["early"]["budgets"] for p in participants]
    r = np.asarray([[b["r"]["p10"] for b in row] for row in rows])
    d = np.asarray([[b["rms_pct"]["median"] for b in row] for row in rows])
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.9), layout="constrained")
    for ax, values, label, threshold in zip(axes, [r, d], ["Lower-decile waveform correlation", "Median RMS discrepancy (%)"], [0.8, 20]):
        for values_one in values:
            ax.plot(budgets, values_one, color="#bfc5c6", linewidth=0.7, alpha=0.8)
        ax.plot(budgets, np.median(values, axis=0), color=TEAL, marker="o", linewidth=2, label="Median across participants")
        ax.axhline(threshold, color="#777777", linestyle="--", linewidth=0.8, label="Illustrative review rule")
        ax.set(xlabel="Trials per disjoint group (2n used)", ylabel=label, xticks=budgets)
    axes[0].set(ylim=(-1.03, 1.03))
    axes[1].set_ylim(bottom=0)
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.suptitle("C3, 20–60 ms: trial budget sensitivity", fontsize=12)
    fig.get_layout_engine().set(rect=(0, 0.09, 1, 0.91))
    fig.text(0.5, 0.015, "22 participants; 100 disjoint splits within each participant and budget. Gray lines are participants, not confidence bands.", ha="center", fontsize=8)
    fig.savefig(destination / "trial-budget.svg", metadata={"Date": None})
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8.2, 6.3), sharey=True, layout="constrained")
    y = np.arange(len(participants))
    axes[0].scatter(r[:, -1], y, color=TEAL, s=22)
    axes[1].scatter(d[:, -1], y, color=TEAL, s=22)
    axes[0].axvline(0.8, linestyle="--", color="#777777", linewidth=0.8)
    axes[1].axvline(20, linestyle="--", color="#777777", linewidth=0.8)
    axes[0].set(xlabel="Lower-decile waveform correlation", xlim=(0.45, 1.02), yticks=y, yticklabels=[p["id"] for p in participants])
    axes[1].set(xlabel="Median RMS discrepancy (%)", xlim=(0, max(d[:, -1]) * 1.15))
    axes[0].invert_yaxis()
    for ax in axes:
        ax.grid(axis="y", color="#eeeeee", linewidth=0.5)
        ax.set_axisbelow(True)
    fig.suptitle("C3, 20–60 ms: two dimensions of agreement at n = 50", fontsize=12)
    fig.get_layout_engine().set(rect=(0, 0.07, 1, 0.93))
    fig.text(0.5, 0.012, "Each row is one participant. Dashed thresholds are illustrative, not validated acceptance criteria.", ha="center", fontsize=8)
    fig.savefig(destination / "participant-review.svg", metadata={"Date": None})
    plt.close(fig)

    participant = participants[0]  # S01, fixed lexical example, never result-selected.
    readout = participant["readouts"]["C3"]["early"]
    example = readout["budgets"][-1]["example"]
    t = np.asarray(payload["meta"]["time_ms"])
    mean = np.asarray(participant["full_mean_uv"]["C3"])
    mask = (t >= 20 - 1e-8) & (t <= 60 + 1e-8)
    fig, ax = plt.subplots(figsize=(7, 3.8), layout="constrained")
    ax.plot(readout["time_ms"], example["a_uv"], color=TEAL, linewidth=2, label="Group A: 50 pulses")
    ax.plot(readout["time_ms"], example["b_uv"], color="#333333", linewidth=1.5, linestyle="--", label="Group B: 50 different pulses")
    ax.plot(t[mask], mean[mask], color="#b5b5b5", linewidth=1.2, label="All retained pulses: context only")
    ax.axhline(0, color="#dddddd", linewidth=0.6)
    ax.set(xlabel="Time relative to pulse (ms)", ylabel="Response (µV)", title="S01, C3: first seeded disjoint split (20–60 ms)")
    ax.legend(frameon=False, fontsize=8)
    fig.get_layout_engine().set(rect=(0, 0.08, 1, 0.92))
    fig.text(0.5, 0.012, "The example is fixed before inspecting results. Agreement does not establish a neural-specific response.", ha="center", fontsize=8)
    fig.savefig(destination / "disjoint-example.svg", metadata={"Date": None})
    plt.close(fig)
