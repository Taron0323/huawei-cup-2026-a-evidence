#!/usr/bin/env python3
"""Render evidence-bound V0.7.1 plots from the read-only analysis CSVs."""
from __future__ import annotations
import argparse, csv
from pathlib import Path
import matplotlib.pyplot as plt


def read(path: Path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--analysis', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args=ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    core=read(args.analysis/'core_summary.csv')
    src=read(args.analysis/'candidate_sources.csv')
    plt.rcParams.update({'font.family':'DejaVu Sans','axes.unicode_minus':False,'font.size':9})

    # Mean speedup over 95 complete cases; profile-only large graphs are excluded by source table.
    fig, ax = plt.subplots(figsize=(6.4,3.7))
    styles={'1':('#2563eb','Problem 1 (A)'),'2':('#dc2626','Problem 2 (B)'),'3':('#059669','Problem 3 (C)')}
    for p,(color,label) in styles.items():
        g=sorted([r for r in core if r['problem']==p], key=lambda r:int(r['cores']))
        ax.plot([int(r['cores']) for r in g],[float(r['mean_speedup']) for r in g],marker='o',lw=2,color=color,label=label)
    ax.set_xlabel('Cores K'); ax.set_ylabel('Mean speedup'); ax.set_xticks([1,2,3,4,5]); ax.grid(alpha=.22); ax.legend(frameon=False,ncol=3,loc='upper left')
    fig.tight_layout(); fig.savefig(args.output/'v071_speedup_by_problem.pdf'); fig.savefig(args.output/'v071_speedup_by_problem.png',dpi=220); plt.close(fig)

    fig, ax1=plt.subplots(figsize=(6.4,3.7)); ax2=ax1.twinx()
    g=sorted([r for r in core if r['problem']=='3'], key=lambda r:int(r['cores']))
    x=[int(r['cores']) for r in g]
    ax1.plot(x,[float(r['mean_same_plan_cache_speedup']) for r in g],marker='o',lw=2,color='#7c3aed',label='Same-plan Cache speedup')
    ax2.plot(x,[100*float(r['byte_weighted_cache_hit_rate']) for r in g],marker='s',lw=2,color='#f59e0b',label='Byte-weighted hit rate')
    ax1.set_xlabel('Cores K'); ax1.set_ylabel('Cache speedup'); ax2.set_ylabel('Hit rate (%)'); ax1.set_xticks(x); ax1.grid(alpha=.22)
    lines=ax1.lines+ax2.lines; ax1.legend(lines,[l.get_label() for l in lines],frameon=False,loc='upper left')
    fig.tight_layout(); fig.savefig(args.output/'v071_cache_by_core.pdf'); fig.savefig(args.output/'v071_cache_by_core.png',dpi=220); plt.close(fig)

    # Candidate coverage: official full rows versus profile-only rows, by problem.
    sums={}
    for r in src:
        p=r['problem']; sums.setdefault(p,[0,0])
        sums[p][0]+=int(r['candidate_rows']); sums[p][1]+=int(r['successful_rows'])
    fig, ax=plt.subplots(figsize=(5.7,3.6)); labels=['Problem 1 (A)','Problem 2 (B)','Problem 3 (C)']; ps=['1','2','3']; full=[sums[p][1] for p in ps]; profile=[sums[p][0]-sums[p][1] for p in ps]
    xx=range(3); ax.bar(xx,full,color='#0f766e',label='Full official evaluation'); ax.bar(xx,profile,bottom=full,color='#cbd5e1',label='Profile-only'); ax.set_xticks(list(xx),labels); ax.set_ylabel('Candidate rows'); ax.legend(frameon=False); ax.grid(axis='y',alpha=.22); fig.tight_layout(); fig.savefig(args.output/'v071_candidate_coverage.pdf'); fig.savefig(args.output/'v071_candidate_coverage.png',dpi=220); plt.close(fig)

if __name__=='__main__': main()
