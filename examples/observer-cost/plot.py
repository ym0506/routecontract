#!/usr/bin/env python3
"""Plot completed block means. Requires matplotlib; never plots smoke/partial runs as results."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads((args.result_directory / "summary.json").read_text())
    receipt = json.loads((args.result_directory / "run.json").read_text())
    if summary["status"] != "EXPLORATORY_RUN_COMPLETE" or receipt["status"] != summary["status"]:
        parser.error("Only a completed full experiment can be plotted")
    cells = summary["cells"]
    expected = {(b, q, c) for b in (1, 2, 3) for q in ("equality", "range")
                for c in ("absent", "idle", "checked")}
    actual = {(c["block"], c["query"], c["condition"]) for c in cells}
    if len(cells) != 18 or actual != expected:
        parser.error("Expected all eighteen distinct block/query/condition measurements")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(10, 7.4))
    colors = ("#667085", "#277DA1", "#A56408")
    labels = ("Absent", "Installed, idle", "Capture + checks")
    for col, query in enumerate(("equality", "range")):
        for row, (key, label, scale) in enumerate((
                ("microsecondsPerOp", "Mean operation time (µs/op)", 1),
                ("allocatedBytesPerOp", "Estimated allocation (KiB/op)", 1 / 1024))):
            ax = axes[row, col]
            for x, condition in enumerate(("absent", "idle", "checked")):
                values = sorted((c for c in cells if c["condition"] == condition and c["query"] == query),
                                key=lambda c: c["block"])
                ax.scatter([x - .08, x, x + .08], [c[key] * scale for c in values],
                           color=colors[x], s=48, zorder=3)
            ax.set_xticks(range(3), labels, fontsize=9)
            ax.set_ylabel(label, fontsize=10)
            upper = max(c[key] * scale for c in cells if c["query"] == query)
            ax.set_ylim(0, upper * 1.15)
            ax.grid(axis="y", alpha=.2)
            ax.spines[["top", "right"]].set_visible(False)
            if row == 0:
                ax.set_title("Equality query" if query == "equality" else "Same-value range query", fontsize=12)
    fig.suptitle("RouteContract 0.1.3 · exploratory MySQL observer-cost experiment", fontsize=14, y=.98)
    fig.text(.5, .035, "Each dot: one fresh JVM trial (left to right: blocks 1–3); 5 × 1 s measurements after 5 × 1 s warmup.\n"
             "Three rotated blocks · one worker · Java 17 / ShardingSphere 5.5.3 / MySQL 8.4.11\n"
             "Local synthetic workload; includes result assertions. Allocation is not retained heap.",
             ha="center", fontsize=9, color="#475467", linespacing=1.5)
    fig.tight_layout(rect=(.01, .14, .99, .94), h_pad=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=170, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
