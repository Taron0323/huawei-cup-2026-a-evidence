"""Fresh finite candidate search for the final idea."""

from __future__ import annotations

from collections import defaultdict
import copy
from typing import Any

from .plan import canonical_plan, groups_from_plan, plan_key, seed_plans, validate_plan
from .scoring import light_score


def _group_maps(plan):
    groups = defaultdict(list)
    for node, group in plan["node_to_subgraph"].items():
        groups[int(group)].append(int(node))
    core_of = {int(group): core for core, sequence in enumerate(plan["core_schedules"]) for group in sequence}
    return groups, core_of


def _rebuild(mapping, schedules, view, cores, scene):
    candidate = canonical_plan(mapping, schedules)
    validate_plan(view, candidate, cores, scene)
    return candidate


def local_variants(view, base, cores, scene):
    """Generate deterministic ordinary, capacity and timing representatives."""
    variants = [("base", base, "seed")]
    groups, core_of = _group_maps(base)
    schedules = [list(x) for x in base["core_schedules"]]
    # Move the first movable block to the least loaded other core.
    if len(groups) > 1 and cores > 1:
        loads = {core: sum(int(view["ops"][str(node)].get("cycles", 0)) for g in seq for node in groups[g]) for core, seq in enumerate(schedules)}
        source = max(range(cores), key=lambda c: (loads[c], -c))
        target = min((c for c in range(cores) if c != source), key=lambda c: (loads[c], c))
        if schedules[source]:
            moved = schedules[source][0]
            edited = [list(x) for x in schedules]
            edited[source].remove(moved)
            edited[target].append(moved)
            try:
                variants.append(("move", _rebuild(base["node_to_subgraph"], edited, view, cores, scene), "ordinary"))
            except ValueError:
                pass
    # Merge adjacent blocks on one core.  This is the resident-domain move.
    for core, seq in enumerate(schedules):
        if len(seq) >= 2:
            left, right = seq[0], seq[1]
            mapping = dict(base["node_to_subgraph"])
            for node, group in mapping.items():
                if int(group) == int(right):
                    mapping[node] = int(left)
            edited = [list(x) for x in schedules]
            edited[core] = [x for x in edited[core] if x != right]
            try:
                variants.append(("aggregate", _rebuild(mapping, edited, view, cores, scene), "aggregate"))
            except ValueError:
                pass
            break
    # Reorder adjacent blocks for a capacity or FIFO timing alternative.
    for core, seq in enumerate(schedules):
        if len(seq) >= 2:
            edited = [list(x) for x in schedules]
            edited[core][0], edited[core][1] = edited[core][1], edited[core][0]
            try:
                variants.append(("reorder", _rebuild(base["node_to_subgraph"], edited, view, cores, scene), "timing" if scene == "C" else "capacity"))
            except ValueError:
                pass
            break
    unique = []
    seen = set()
    for name, plan, source in variants:
        key = plan_key(plan)
        if key not in seen:
            unique.append((name, plan, source))
            seen.add(key)
    return unique


def generate_candidates(view, cores, scene, config, *, base_plan=None):
    seeds = seed_plans(view, cores, scene) if base_plan is None else {"base": base_plan}
    candidates = []
    seen = set()
    for seed_name, seed in seeds.items():
        variants = local_variants(view, seed, cores, scene)
        if scene == "C":
            variants.extend(cache_variants(view, seed, cores, scene))
        for name, plan, source in variants:
            key = plan_key(plan)
            if key in seen:
                continue
            item = {"candidate": f"{seed_name}_{name}", "source": source, "plan": plan, "light": light_score(view, plan, scene, config)}
            candidates.append(item)
            seen.add(key)
    candidates.sort(key=lambda item: (tuple(item["light"]["score"]), item["candidate"]))
    return candidates


def cache_variants(view, base, cores, scene):
    """Generate explicit aggregate/disperse/cache-timing candidates from B."""
    mapping = {int(node): int(group) for node, group in base["node_to_subgraph"].items()}
    groups, core_of = _group_maps(base)
    schedules = [list(x) for x in base["core_schedules"]]
    variants = []
    shared = []
    for tid, users in view["tensor_consumers"].items():
        consumer_cores = {core_of[mapping[int(node)]] for node in users if int(node) in mapping}
        if len(consumer_cores) >= 2:
            shared.append((int(view["tensor_sizes"].get(str(tid), 0)), int(tid), users, consumer_cores))
    for _size, _tid, users, consumer_cores in sorted(shared, reverse=True)[:8]:
        target = min(consumer_cores)
        moved_groups = {mapping[int(node)] for node in users if int(node) in mapping and core_of[mapping[int(node)]] != target}
        if moved_groups:
            edited = [list(seq) for seq in schedules]
            for source in consumer_cores:
                if source == target:
                    continue
                for group in list(edited[source]):
                    if group in moved_groups:
                        edited[source].remove(group)
                        edited[target].append(group)
            try:
                variants.append((f"aggregate_tid_{_tid}", _rebuild(mapping, edited, view, cores, scene), "aggregate"))
            except ValueError:
                pass
        # A timing alternative keeps the domains but moves the relevant group
        # to the opposite end of its current core list.
        for group in sorted({mapping[int(node)] for node in users if int(node) in mapping}):
            core = core_of[group]
            if group in schedules[core] and len(schedules[core]) >= 2:
                edited = [list(seq) for seq in schedules]
                edited[core].remove(group)
                edited[core].append(group)
                try:
                    variants.append((f"timing_tid_{_tid}_group_{group}", _rebuild(mapping, edited, view, cores, scene), "timing"))
                except ValueError:
                    pass
                break
    return variants


def choose_light(candidates):
    if not candidates:
        raise ValueError("no legal candidate")
    return candidates[0]
