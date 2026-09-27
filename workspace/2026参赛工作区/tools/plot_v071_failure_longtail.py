"""Render the V0.7.1 failure/long-tail count figure from saved CSV outputs."""
from pathlib import Path
import csv
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "results/v071_full_20260924_v2_analysis"
OUTPUT = ROOT / "figures/v071_full_20260924_v2/v071_failure_longtail.pdf"


def count_rows(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return sum(1 for _ in csv.DictReader(stream))


def main() -> None:
    failure_count = count_rows(ANALYSIS / "failures.csv")
    long_tail_count = count_rows(ANALYSIS / "long_tail.csv")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(5.8, 3.2))
    labels = ["Failure rows", "Long-tail rows\n(>60 s)"]
    values = [failure_count, long_tail_count]
    bars = ax.bar(labels, values, color=["#4C78A8", "#F58518"], width=0.55)
    ax.set_ylabel("Rows")
    ax.set_title("V0.7.1 candidate execution status")
    ax.set_ylim(0, max(values + [1]) * 1.25)
    ax.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.15, str(value), ha="center", va="bottom")
    fig.tight_layout()
    fig.savefig(OUTPUT, bbox_inches="tight")
    plt.close(fig)
    print(OUTPUT)


if __name__ == "__main__":
    main()
