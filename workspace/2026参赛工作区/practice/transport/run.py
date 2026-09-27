# 本程序及代码是在人工智能工具Codex辅助下完成的合成演练。
# 开发机构OpenAI；精确版本/型号及版本发布日期待核验，见prep/ai_preparation.json。
# 本文件不是正式参赛求解器。独立枚举、约束残差和失败样例见生成的verification.json。
"""Solve a synthetic transport LP and compare against exhaustive enumeration."""

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy
from scipy.optimize import linprog

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]


def metadata(path):
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def enumerate_optimum(supply, demand, cost):
    candidates = []
    for a in range(demand[0] + 1):
        for b in range(demand[1] + 1):
            c = supply[0] - a - b
            top = [a, b, c]
            bottom = [demand[j] - top[j] for j in range(3)]
            if min(top + bottom) < 0 or sum(bottom) != supply[1]:
                continue
            total = sum(cost[0][j] * top[j] + cost[1][j] * bottom[j] for j in range(3))
            candidates.append((total, top + bottom))
    return min(candidates), len(candidates)


def main(run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid run ID")
    output = BASE / "runs" / run_id
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now().astimezone().isoformat()
    data = json.loads((BASE / "input.json").read_text())
    supply, demand, cost = data["supply"], data["demand"], np.array(data["cost"], dtype=float)
    constraints = np.array([[1, 1, 1, 0, 0, 0], [0, 0, 0, 1, 1, 1],
                            [1, 0, 0, 1, 0, 0], [0, 1, 0, 0, 1, 0], [0, 0, 1, 0, 0, 1]])
    rhs = np.array(supply + demand)
    solve = lambda values, bounds: linprog(values.ravel(), A_eq=constraints, b_eq=bounds, bounds=(0, None), method="highs")
    solution = solve(cost, rhs)
    if not solution.success:
        write_json(output / "failure.json", {"status": solution.status, "message": solution.message})
        raise RuntimeError(solution.message)
    flow = solution.x.reshape(2, 3)
    (oracle_value, oracle_flow), candidate_count = enumerate_optimum(supply, demand, data["cost"])
    repeat = solve(cost, rhs)
    infeasible = solve(cost, rhs + np.array([0, 0, 0, 0, 1]))
    perturbed_cost = cost.copy()
    perturbed_cost[0, 0] += 1
    perturbed = solve(perturbed_cost, rhs)
    perturbed_oracle, _ = enumerate_optimum(supply, demand, perturbed_cost.tolist())
    residual = float(np.max(np.abs(constraints @ solution.x - rhs)))
    checks = [
        {"id": "conservation", "method": "all supply and demand equations", "residual": residual, "tolerance": 1e-9, "passed": residual <= 1e-9},
        {"id": "nonnegative", "minimum": float(flow.min()), "passed": bool(flow.min() >= -1e-9)},
        {"id": "independent_optimum", "method": "exhaustive feasible integer flows", "candidate_count": candidate_count,
         "oracle": oracle_value, "residual": abs(float(solution.fun) - oracle_value), "passed": abs(solution.fun - oracle_value) <= 1e-9},
        {"id": "repeat", "passed": bool(repeat.success and abs(repeat.fun - solution.fun) <= 1e-9)},
        {"id": "infeasible_detected", "solver_status": int(infeasible.status), "passed": infeasible.status == 2},
        {"id": "cost_perturbation", "objective": float(perturbed.fun), "oracle": perturbed_oracle[0],
         "passed": bool(perturbed.success and abs(perturbed.fun - perturbed_oracle[0]) <= 1e-9)},
    ]
    with (output / "flows.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["route", "source", "destination", "flow", "unit_cost", "total_cost"])
        for i in range(2):
            for j in range(3):
                writer.writerow([f"S{i+1}-D{j+1}", i+1, j+1, float(flow[i,j]), float(cost[i,j]), float(flow[i,j]*cost[i,j])])
    (output / "metrics.csv").write_text("metric,value,unit\nobjective," + str(float(solution.fun)) + ",synthetic currency\n")
    fig, ax = plt.subplots(figsize=(7, 2.8), layout="constrained")
    positions = np.arange(3)
    ax.bar(positions - .18, flow[0], width=.36, color="#197278", label="Source 1")
    ax.bar(positions + .18, flow[1], width=.36, color="#c45b45", label="Source 2")
    ax.set(xticks=positions, xticklabels=["D1", "D2", "D3"], ylabel="Synthetic units", title="Synthetic transport allocation")
    ax.legend(frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(output / "allocation.pdf")
    fig.savefig(output / "allocation.png", dpi=170)
    plt.close(fig)
    table_rows = "\n".join(f"S{i+1} & " + " & ".join(f"{v:g}" for v in flow[i]) + r" \\" for i in range(2))
    report = r"""\documentclass[a4paper,11pt]{article}
\usepackage[margin=22mm]{geometry}
\usepackage{amsmath,booktabs,graphicx}
\begin{document}
\section*{Synthetic Transport Workflow Rehearsal}
\textbf{Preparation only. These are not official contest data or results.}

Two sources supply 7 and 5 synthetic units. Three destinations demand 3, 4, and 5 units.
The objective is $\min \sum_{i,j}c_{ij}x_{ij}$ subject to exact supply and demand balances and $x_{ij}\geq0$.
SciPy/HiGHS solves the LP. A separate exhaustive enumeration checks every feasible integer allocation.
For this transport instance, integral supplies and demands admit an integral LP optimum.

\subsection*{Computed result}
The minimum cost is VALUE synthetic currency units. Conservation residual is RESIDUAL.
The independent enumeration examined COUNT feasible allocations and obtained the same optimum.
\begin{center}\begin{tabular}{lrrr}\toprule
Source & D1 & D2 & D3\\\midrule
ROWS
\bottomrule\end{tabular}\end{center}
\includegraphics[width=\linewidth]{allocation.pdf}
\subsection*{Verification and provenance}
All six checks passed: balance, nonnegativity, independent optimum, repeat solve,
infeasible-input detection, and cost perturbation checked against enumeration.
CSV results, code/input hashes, environment, solver status, and numerical residuals are retained beside this report.

AI assistance: Codex, OpenAI; exact model version and release date remain unverified.
This rehearsal does not establish formal contest disclosure compliance or human approval.
\end{document}
"""
    for key, value in {"VALUE": f"{solution.fun:g}", "RESIDUAL": f"{residual:g}", "COUNT": str(candidate_count), "ROWS": table_rows}.items():
        report = report.replace(key, value)
    (output / "report.tex").write_text(report)
    passed = all(c["passed"] for c in checks)
    write_json(output / "verification.json", {"phase": "SYNTHETIC_PRACTICE", "run_id": run_id, "checks": checks,
               "files": [metadata(p) for p in (BASE / "input.json", Path(__file__).resolve(), output / "flows.csv", output / "metrics.csv", output / "allocation.pdf")],
               "human_review": "PENDING", "passed": passed})
    if not passed:
        raise RuntimeError("Synthetic verification failed; see verification.json")
    command = ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "report.tex"]
    compiled = subprocess.run(command, cwd=output, capture_output=True, text=True)
    (output / "compile.log").write_text(compiled.stdout + compiled.stderr)
    compiled.check_returncode()
    write_json(output / "run.json", {"phase": "SYNTHETIC_PRACTICE", "run_id": run_id, "started_at": started,
               "ended_at": datetime.now().astimezone().isoformat(), "command": "python practice/transport/run.py --run-id " + run_id,
               "environment": {"python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__, "matplotlib": matplotlib.__version__, "platform": platform.platform()},
               "randomness": "deterministic; no RNG", "solver": "HiGHS via scipy.optimize.linprog", "solver_status": int(solution.status), "exit_code": 0,
               "inputs": [metadata(BASE / "input.json")], "code": [metadata(Path(__file__).resolve())],
               "outputs": [metadata(output / name) for name in ("flows.csv", "metrics.csv", "verification.json", "allocation.pdf", "allocation.png", "report.tex", "report.pdf", "compile.log")]})
    print(json.dumps({"run_id": run_id, "objective": float(solution.fun), "checks": len(checks), "passed": passed}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    main(parser.parse_args().run_id)
