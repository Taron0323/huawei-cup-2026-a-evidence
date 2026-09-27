# 人工智能工具辅助编程声明：本程序及代码在人工智能工具辅助下完成。
# 工具名称：OpenAI Codex；版本/型号：GPT-6 系列（准确会话型号以平台记录为准）；
# 开发机构：OpenAI；版本发布日期：以实际平台记录为准。
# 队员已对算法、参数、输入输出和官方评估结果进行人工核对，并保留后处理记录。

"""Fresh finite candidate search for the final idea."""

from __future__ import annotations

from collections import defaultdict
import copy
from typing import Any

from .plan import _split_order, canonical_plan, groups_from_plan, legacy_seed_plans, plan_key, seed_plans, validate_plan
from .scoring import light_score


def _group_maps(plan):
    groups = defaultdict(list)
    for node, group in plan["node_to_subgraph"].items():
        groups[int(group)].append(int(node))
    core_of = {int(group): core for core, sequence in enumerate(plan["core_schedules"]) for group in sequence}
    return groups, core_of


def _rebuild(mapping, schedules, view, cores):
    candidate = canonical_plan(mapping, schedules)
    validate_plan(view, candidate, cores)
    return candidate


def _loads(view, plan):
    groups, _ = _group_maps(plan)
    return {
        core: sum(max(1, int(view["ops"][str(node)].get("cycles", 0))) for group in sequence for node in groups[int(group)])
        for core, sequence in enumerate(plan["core_schedules"])
    }


def _move_node(view, base, node, target_core, position, cores):
    """Split one consumer operation into a new group on another core."""
    mapping = {int(key): int(value) for key, value in base["node_to_subgraph"].items()}
    source_group = mapping[int(node)]
    schedules = [list(sequence) for sequence in base["core_schedules"]]
    source_core = next(core for core, sequence in enumerate(schedules) if source_group in sequence)
    if source_core == target_core:
        return None
    source_position = schedules[source_core].index(source_group)
    mapping[int(node)] = max(mapping.values(), default=-1) + 1
    schedules[source_core].remove(source_group)
    remaining_nodes = [key for key, value in mapping.items() if value == source_group]
    if remaining_nodes:
        schedules[source_core].insert(min(source_position, len(schedules[source_core])), source_group)
    position = max(0, min(int(position), len(schedules[target_core])))
    schedules[target_core].insert(position, mapping[int(node)])
    try:
        return _rebuild(mapping, schedules, view, cores)
    except ValueError:
        return None


def _move_group_position(view, base, group, position):
    schedules = [list(sequence) for sequence in base["core_schedules"]]
    core = next((index for index, sequence in enumerate(schedules) if int(group) in sequence), None)
    if core is None:
        return None
    sequence = schedules[core]
    sequence.remove(int(group))
    sequence.insert(max(0, min(int(position), len(sequence))), int(group))
    try:
        return _rebuild(base["node_to_subgraph"], schedules, view, len(schedules))
    except ValueError:
        return None


def _move_group_core(view, base, group, target_core, position, cores):
    schedules = [list(sequence) for sequence in base["core_schedules"]]
    source_core = next((index for index, sequence in enumerate(schedules) if int(group) in sequence), None)
    if source_core is None or source_core == target_core:
        return None
    schedules[source_core].remove(int(group))
    schedules[target_core].insert(max(0, min(int(position), len(schedules[target_core]))), int(group))
    try:
        return _rebuild(base["node_to_subgraph"], schedules, view, cores)
    except ValueError:
        return None


def _group_dependency_maps(view, plan):
    """Return group membership, core placement, and contracted predecessors."""
    mapping = {int(node): int(group) for node, group in plan["node_to_subgraph"].items()}
    groups, core_of = _group_maps(plan)
    group_preds = {int(group): set() for group in groups}
    for node, parents in view["preds"].items():
        node = int(node)
        if node not in mapping:
            continue
        target = mapping[node]
        for parent in parents:
            parent = int(parent)
            if parent in mapping and mapping[parent] != target:
                group_preds[target].add(mapping[parent])
    return mapping, groups, core_of, group_preds


def _group_reuse_scores(view, plan, config):
    """Score groups that expose repeated small-tensor reads after a split."""
    mapping, groups, core_of, _ = _group_dependency_maps(view, plan)
    sizes = {int(tid): int(size) for tid, size in view["tensor_sizes"].items()}
    capacity = int(config["cache"]["capacity"])
    reuse = defaultdict(int)
    shared = defaultdict(int)
    for tid, users in view["tensor_consumers"].items():
        tid = int(tid)
        size = sizes.get(tid, 0)
        if size <= 0 or size > capacity:
            continue
        user_groups = defaultdict(list)
        for node in users:
            node = int(node)
            if node in mapping:
                user_groups[core_of[mapping[node]]].append(mapping[node])
        for core, group_ids in user_groups.items():
            unique = sorted(set(group_ids))
            if len(unique) > 1:
                for group in unique:
                    reuse[group] += size * (len(unique) - 1)
            if len(user_groups) > 1:
                for group in unique:
                    shared[group] += size * (len(user_groups) - 1)
    return reuse, shared


def _reorder_core(view, base, core, mode, cores, config):
    """Topologically reorder one core with a deterministic reuse priority."""
    schedules = [list(sequence) for sequence in base["core_schedules"]]
    sequence = schedules[core]
    if len(sequence) < 2:
        return None
    _mapping, groups, core_of, group_preds = _group_dependency_maps(view, base)
    reuse, shared = _group_reuse_scores(view, base, config)
    ops = view["ops"]
    weights = {
        group: sum(max(1, int(ops[str(node)].get("cycles", 0))) for node in nodes)
        for group, nodes in groups.items()
    }
    ranks = {int(node): index for index, node in enumerate(map(int, view["r_order"]))}
    node_rank = {
        group: min((ranks.get(node, len(ranks)) for node in nodes), default=len(ranks))
        for group, nodes in groups.items()
    }
    local = set(sequence)
    predecessors = {group: {parent for parent in group_preds[group] if parent in local} for group in local}
    ready = {group for group in local if not predecessors[group]}
    ordered = []
    while ready:
        if mode == "cache":
            key = lambda group: (-shared[group], -reuse[group], node_rank[group], group)
        elif mode == "release":
            key = lambda group: (-reuse[group], weights[group], node_rank[group], group)
        else:
            key = lambda group: (weights[group], node_rank[group], group)
        group = min(ready, key=key)
        ready.remove(group)
        ordered.append(group)
        for child in local:
            if group in predecessors[child]:
                predecessors[child].remove(group)
                if not predecessors[child]:
                    ready.add(child)
    if len(ordered) != len(sequence) or ordered == sequence:
        return None
    schedules[core] = ordered
    try:
        return _rebuild(base["node_to_subgraph"], schedules, view, cores)
    except ValueError:
        return None


def split_same_core_variants(view, base, cores, config):
    """Split a resident group while retaining one core, exposing new timing states.

    The official Step2 spill pass is sensitive to the resulting operation order.
    Splitting is therefore limited to a few high-weight groups and legal
    topological orders; the official evaluator remains the authority.
    """
    _mapping, groups, core_of, _ = _group_dependency_maps(view, base)
    topo_orders = [
        ("topo", [int(node) for node in view["topological"]]),
        ("release", [int(node) for node in view["r_order"]]),
        ("height", [int(node) for node in view["h_order"]]),
    ]
    ops = view["ops"]
    ranked_groups = sorted(
        groups,
        key=lambda group: (
            -sum(max(1, int(ops[str(node)].get("cycles", 0))) for node in groups[group]),
            -len(groups[group]),
            group,
        ),
    )
    variants = []
    seen = set()
    for group in ranked_groups[:6]:
        source_core = core_of[group]
        group_nodes = set(groups[group])
        for order_name, order in topo_orders:
            ordered_nodes = [node for node in order if node in group_nodes]
            if len(ordered_nodes) < 4:
                continue
            for parts in (2, 4):
                if len(ordered_nodes) < parts:
                    continue
                mapping = {int(node): int(value) for node, value in base["node_to_subgraph"].items()}
                schedules = [list(sequence) for sequence in base["core_schedules"]]
                position = schedules[source_core].index(group)
                chunk_ids = [max(mapping.values(), default=-1) + index + 1 for index in range(parts)]
                for index, node in enumerate(ordered_nodes):
                    chunk = min(parts - 1, index * parts // len(ordered_nodes))
                    mapping[node] = chunk_ids[chunk]
                schedules[source_core][position:position + 1] = chunk_ids
                try:
                    candidate = _rebuild(mapping, schedules, view, cores)
                except ValueError:
                    continue
                key = plan_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                variants.append((f"split_{order_name}_g{group}_p{parts}", candidate, "timing"))
                if len(variants) >= 24:
                    return variants
    return variants


def core_order_variants(view, base, cores, config):
    """Try reuse-aware legal orders on cores that already have several groups."""
    variants = []
    seen = set()
    for core in range(cores):
        for mode in ("cache", "release", "short"):
            candidate = _reorder_core(view, base, core, mode, cores, config)
            if candidate is None:
                continue
            key = plan_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            variants.append((f"order_{mode}_core_{core}", candidate, "timing"))
    return variants


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
                variants.append(("move", _rebuild(base["node_to_subgraph"], edited, view, cores), "ordinary"))
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
                variants.append(("aggregate", _rebuild(mapping, edited, view, cores), "aggregate"))
            except ValueError:
                pass
            break
    # Reorder adjacent blocks for a capacity or FIFO timing alternative.
    for core, seq in enumerate(schedules):
        if len(seq) >= 2:
            edited = [list(x) for x in schedules]
            edited[core][0], edited[core][1] = edited[core][1], edited[core][0]
            try:
                variants.append(("reorder", _rebuild(base["node_to_subgraph"], edited, view, cores), "timing" if scene == "C" else "capacity"))
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


def capacity_variants(view, base, cores, config):
    """Generate a bounded, explicitly labelled capacity-risk portfolio.

    The light pressure value is only a ranking signal.  These candidates move
    groups touching large tensors to the front or back of their current core,
    changing the operation-level lifetime proxy and giving the official Step2
    spill pass an actual opportunity to confirm or reject the edit.  Keeping
    this source separate prevents capacity pressure from disappearing behind a
    three-way lexicographic tie-break.
    """
    mapping, groups, core_of, _ = _group_dependency_maps(view, base)
    sizes = {int(tid): int(size) for tid, size in view["tensor_sizes"].items()}
    scores = defaultdict(int)
    for tid, users in view["tensor_consumers"].items():
        tid = int(tid)
        size = sizes.get(tid, 0)
        if size <= 0:
            continue
        touched = {mapping[int(node)] for node in users if int(node) in mapping}
        if len(touched) < 2:
            continue
        # A large tensor consumed across several groups is a direct source of
        # overlapping residency; retain it even when the current peak proxy
        # happens to be below the configured capacity.
        for group in touched:
            scores[group] += size * (len(touched) - 1)
    if not scores:
        # Preserve an explicit capacity source for ordinary multi-group plans
        # so the selector can report that the quota was considered.
        for group, nodes in groups.items():
            scores[group] = sum(max(1, int(view["ops"][str(node)].get("cycles", 0))) for node in nodes)
    variants = []
    seen = set()
    for group, _risk in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:12]:
        core = core_of[group]
        sequence_len = len(base["core_schedules"][core])
        if sequence_len < 2:
            continue
        for position, label in ((0, "front"), (sequence_len, "back")):
            candidate = _move_group_position(view, base, group, position)
            if candidate is None:
                continue
            key = plan_key(candidate)
            if key in seen or key == plan_key(base):
                continue
            seen.add(key)
            variants.append((f"capacity_g{group}_{label}", candidate, "capacity"))
            if len(variants) >= 24:
                return variants
    return variants


def _group_move_variants(view, base, cores):
    groups, core_of = _group_maps(base)
    loads = _loads(view, base)
    ranked = sorted(groups, key=lambda group: (-sum(int(view["ops"][str(node)]["cycles"]) for node in groups[group]), group))
    result = []
    for group in ranked[:8]:
        targets = sorted((core for core in range(cores) if core != core_of[group]), key=lambda core: (loads[core], core))[:2]
        for target in targets:
            for position in sorted({0, len(base["core_schedules"][target])}):
                plan = _move_group_core(view, base, group, target, position, cores)
                if plan is not None:
                    result.append((f"move_g{group}_c{target}_p{position}", plan, "ordinary"))
    return result


def _split_group_variants(view, base, cores):
    if cores == 1:
        return []
    mapping, groups, core_of, _ = _group_dependency_maps(view, base)
    loads = _loads(view, base)
    ranked = sorted(groups, key=lambda group: (-sum(int(view["ops"][str(node)]["cycles"]) for node in groups[group]), group))
    result = []
    for group in ranked[:4]:
        members = set(groups[group])
        if len(members) < 4:
            continue
        order = [int(node) for node in view["h_order"] if int(node) in members]
        halves = _split_order(view, order, 2)
        targets = sorted((core for core in range(cores) if core != core_of[group]), key=lambda core: (loads[core], core))[:2]
        for half_index, half in enumerate(halves):
            for target in targets:
                for position in sorted({0, len(base["core_schedules"][target])}):
                    edited_mapping = dict(mapping)
                    new_group = max(mapping.values()) + 1
                    for node in half:
                        edited_mapping[node] = new_group
                    schedules = [list(sequence) for sequence in base["core_schedules"]]
                    schedules[target].insert(position, new_group)
                    try:
                        plan = _rebuild(edited_mapping, schedules, view, cores)
                    except ValueError:
                        continue
                    result.append((f"split_g{group}_h{half_index}_c{target}_p{position}", plan, "ordinary"))
    return result


def _merge_variants(view, base, cores):
    result = []
    for core, sequence in enumerate(base["core_schedules"]):
        for left, right in zip(sequence, sequence[1:]):
            mapping = {int(node): (left if int(group) == right else int(group)) for node, group in base["node_to_subgraph"].items()}
            schedules = [[group for group in groups if group != right] for groups in base["core_schedules"]]
            try:
                plan = _rebuild(mapping, schedules, view, cores)
            except ValueError:
                continue
            result.append((f"merge_g{left}_{right}", plan, "ordinary"))
            if len(result) >= 12:
                return result
    return result


def _boundary_node_variants(view, base, cores, scene):
    if cores == 1:
        return []
    mapping, _groups, core_of, _ = _group_dependency_maps(view, base)
    loads = _loads(view, base)
    score = defaultdict(int)
    for tid, consumers in view["tensor_consumers"].items():
        nodes = [int(node) for node in view["tensor_producers"].get(tid, ())] + [int(node) for node in consumers]
        domains = {mapping[node] for node in nodes if node in mapping}
        if len(domains) > 1:
            for node in nodes:
                if node in mapping:
                    score[node] += int(view["tensor_sizes"][tid])
    ranked = sorted(score, key=lambda node: (-score[node], -int(view["depth"].get(str(node), 0)), node))[:32]
    result = []
    for node in ranked:
        neighbors = [int(other) for other in view["preds"][str(node)] + view["succs"][str(node)]]
        targets = sorted({core_of[mapping[other]] for other in neighbors if other in mapping and core_of[mapping[other]] != core_of[mapping[node]]})
        targets += [core for core in sorted(range(cores), key=lambda core: (loads[core], core)) if core != core_of[mapping[node]] and core not in targets][:1]
        for target in targets[:2]:
            for position in sorted({0, len(base["core_schedules"][target])}):
                plan = _move_node(view, base, node, target, position, cores)
                if plan is not None:
                    result.append((f"boundary_n{node}_c{target}_p{position}", plan, "ordinary"))
                    if len(result) >= (8 if scene == "A" else 16):
                        return result
    return result


def local_search_variants(view, base, cores, scene, config, limit):
    categories = [
        _group_move_variants(view, base, cores),
        _split_group_variants(view, base, cores),
        _merge_variants(view, base, cores),
        _boundary_node_variants(view, base, cores, scene),
        core_order_variants(view, base, cores, config),
        capacity_variants(view, base, cores, config),
    ]
    result = []
    seen = {plan_key(base)}
    for index in range(max(map(len, categories), default=0)):
        for category in categories:
            if index >= len(category):
                continue
            name, plan, source = category[index]
            key = plan_key(plan)
            if key not in seen:
                result.append((name, plan, source))
                seen.add(key)
                if len(result) >= limit:
                    return result
    return result


def search_representatives(view, initial, cores, scene, config):
    size = int(view["compute_ops"])
    rounds, limit = ((10, 64 if scene == "A" else 48) if size <= 2000 else (2, 48 if scene == "A" else 36) if size <= 10000 else (1, 32 if scene == "A" else 24))
    current = initial
    baseline_pressure = int(initial["light"]["pressure_bytes"])
    ordinary = capacity = None
    scored = []
    seen = {plan_key(initial["plan"])}
    for round_index in range(rounds):
        round_items = []
        for name, plan, source in local_search_variants(view, current["plan"], cores, scene, config, limit):
            key = plan_key(plan)
            if key in seen:
                continue
            seen.add(key)
            item = {"candidate": f"r{round_index + 1}_{name}", "source": source, "plan": plan, "mandatory": False, "light": light_score(view, plan, scene, config)}
            round_items.append(item)
            scored.append(item)
            if int(item["light"]["pressure_bytes"]) < baseline_pressure:
                if capacity is None or (int(item["light"]["pressure_bytes"]), tuple(item["light"]["score"]), key) < (int(capacity["light"]["pressure_bytes"]), tuple(capacity["light"]["score"]), plan_key(capacity["plan"])):
                    capacity = item
        improved = [item for item in round_items if tuple(item["light"]["score"]) < tuple(current["light"]["score"])]
        if not improved:
            break
        current = min(improved, key=lambda item: (tuple(item["light"]["score"]), plan_key(item["plan"])))
        ordinary = current
    return ordinary, capacity, scored


def generate_candidates(view, cores, scene, config, *, base_plan=None, incumbent_plan=None, lower_core_plan=None, warm_start_plan=None):
    if base_plan is None:
        seeds = seed_plans(view, cores, scene, config)
        if scene in {"A", "B"}:
            seeds.update(legacy_seed_plans(view, cores, scene))
        # Keep B's selected plan as the first-class C incumbent while retaining
        # one unedited representative from each other legal start.  The
        # incumbent receives the expensive C-specific edits; alternatives are
        # kept as bounded escape routes so the portfolio does not explode.
        if scene == "C" and incumbent_plan is not None:
            seeds = {"incumbent": incumbent_plan, **seeds}
    else:
        seeds = {"base": base_plan}
    if scene == "B" and warm_start_plan is not None:
        # A's final plan is legal in B and provides a cross-question warm
        # start.  Keep it as a separate seed so the controlled comparison can
        # identify whether the B-specific search improves on it.
        seeds["q1_warm"] = warm_start_plan
    candidates = []
    seen = set()
    for seed_name, seed in seeds.items():
        if (scene == "C" and incumbent_plan is not None and seed_name != "incumbent") or seed_name.startswith("L"):
            variants = [("base", seed, "seed")]
        else:
            # Capacity candidates are inserted first so an identical plan is
            # retained under the explicit source label rather than silently
            # deduplicated as an ordinary timing edit.
            variants = capacity_variants(view, seed, cores, config)
            variants.extend(local_variants(view, seed, cores, scene))
        if scene == "C" and (incumbent_plan is None or seed_name == "incumbent"):
            variants.extend(cache_variants(view, seed, cores))
            variants.extend(cache_delay_variants(view, seed, cores, config))
            variants.extend(leader_skew_variants(view, seed, cores, config))
            variants.extend(disperse_variants(view, seed, cores, config))
            variants.extend(timing_variants(view, seed, cores, config))
            variants.extend(split_same_core_variants(view, seed, cores, config))
            variants.extend(core_order_variants(view, seed, cores, config))
        for name, plan, source in variants:
            key = plan_key(plan)
            if key in seen:
                continue
            item_source = "incumbent" if scene == "C" and seed_name == "incumbent" and name == "base" else "legacy_seed" if seed_name.startswith("L") else source
            item = {
                "candidate": f"{seed_name}_{name}",
                "source": item_source,
                "plan": plan,
                "mandatory": (
                    (name == "base" and scene != "C")
                    or (scene == "C" and seed_name == "incumbent" and name == "base")
                ),
                "light": light_score(view, plan, scene, config),
            }
            candidates.append(item)
            seen.add(key)
    if incumbent_plan is not None and not (scene == "C" and base_plan is None):
        key = plan_key(incumbent_plan)
        if key not in seen:
            candidates.append({
                "candidate": "incumbent_base",
                "source": "incumbent",
                "plan": incumbent_plan,
                "mandatory": True,
                "light": light_score(view, incumbent_plan, scene, config),
            })
            seen.add(key)

    anchor_plans = []
    if scene == "C":
        if incumbent_plan is not None:
            anchor_plans.append(("b_incumbent", incumbent_plan))
    anchor_plans.extend((role, seeds[name]) for role, name in (
        ("whole_graph", f"{scene}0"),
        ("component_pack", f"{scene}1"),
    ) if name in seeds)
    if scene == "B" and warm_start_plan is not None:
        anchor_plans.append(("q1_warm_start", warm_start_plan))
    inherited = lower_core_plan if scene == "C" else incumbent_plan
    if inherited is not None:
        anchor_plans.append(("lower_core", inherited))

    by_plan = {plan_key(item["plan"]): item for item in candidates}
    for item in candidates:
        item["mandatory"] = False
        item["mandatory_rank"] = None
        item["anchor_roles"] = []
    for rank, (role, plan) in enumerate(anchor_plans):
        key = plan_key(plan)
        item = by_plan.get(key)
        if item is None:
            item = {
                "candidate": f"{role}_base",
                "source": role,
                "plan": plan,
                "mandatory": False,
                "mandatory_rank": None,
                "anchor_roles": [],
                "light": light_score(view, plan, scene, config),
            }
            candidates.append(item)
            by_plan[key] = item
        item["mandatory"] = True
        item["mandatory_rank"] = rank if item["mandatory_rank"] is None else min(item["mandatory_rank"], rank)
        item["anchor_roles"].append(role)
    if scene == "C":
        candidates.sort(key=lambda item: (
            tuple(item["light"]["score"]),
            -int(item["light"].get("cache_hit_bytes", 0)),
            -float(item["light"].get("cache_expected_gain", 0.0)),
            item["candidate"],
        ))
    else:
        candidates.sort(key=lambda item: (tuple(item["light"]["score"]), item["candidate"]))
    return candidates


def cache_variants(view, base, cores):
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
                variants.append((f"aggregate_tid_{_tid}", _rebuild(mapping, edited, view, cores), "aggregate"))
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
                    variants.append((f"timing_tid_{_tid}_group_{group}", _rebuild(mapping, edited, view, cores), "timing"))
                except ValueError:
                    pass
                break
    return variants


def _shared_tensors(view, base, config):
    mapping = {int(node): int(group) for node, group in base["node_to_subgraph"].items()}
    _, core_of = _group_maps(base)
    capacity = int(config["cache"]["capacity"])
    shared = []
    for tid, users in view["tensor_consumers"].items():
        tid = int(tid)
        size = int(view["tensor_sizes"].get(str(tid), 0))
        if size <= 0 or size > capacity:
            continue
        valid_users = [int(node) for node in users if int(node) in mapping]
        if len(valid_users) < 2:
            continue
        user_cores = {core_of[mapping[node]] for node in valid_users}
        potential = size * max(0, len(user_cores) - 1)
        structural = size * (len(valid_users) - 1)
        shared.append((potential, structural, size, tid, valid_users, user_cores))
    return sorted(shared, reverse=True)


def disperse_variants(view, base, cores, config):
    """Create legal candidates that deliberately create repeated cross-core reads."""
    if cores < 2:
        return []
    variants = []
    seen = set()
    loads = _loads(view, base)
    for _potential, _structural, size, tid, users, user_cores in _shared_tensors(view, base, config)[:24]:
        groups, core_of = _group_maps(base)
        mapping = {int(node): int(group) for node, group in base["node_to_subgraph"].items()}
        consumer_groups = sorted(
            {mapping[int(node)] for node in users if int(node) in mapping},
            key=lambda group: (
                sum(max(1, int(view["ops"][str(node)].get("cycles", 0))) for node in groups[group]),
                group,
            ),
        )
        target_order = sorted(range(cores), key=lambda core: (loads.get(core, 0), core))
        for group in consumer_groups[:4]:
            source_core = core_of[group]
            for target in [core for core in target_order if core != source_core][: min(3, max(0, cores - 1))]:
                schedule_len = len(base["core_schedules"][target])
                for position in sorted({0, schedule_len // 2, schedule_len}):
                    candidate = _move_group_core(view, base, group, target, position, cores)
                    if candidate is None:
                        continue
                    key = plan_key(candidate)
                    if key in seen:
                        continue
                    seen.add(key)
                    variants.append((f"disperse_group_tid_{tid}_group_{group}_core_{target}_pos_{position}", candidate, "disperse"))
                    if len(variants) >= 160:
                        return variants
        node_order = sorted(users, key=lambda node: (-int(view["ops"][str(node)].get("cycles", 0)), node))[:4]
        for node in node_order:
            source_core = next(core for core, sequence in enumerate(base["core_schedules"]) if mapping[int(node)] in sequence)
            targets = [core for core in target_order if core != source_core]
            for target in targets[: min(3, len(targets))]:
                schedule_len = len(base["core_schedules"][target])
                positions = sorted({0, schedule_len // 2, schedule_len})
                for position in positions:
                    candidate = _move_node(view, base, node, target, position, cores)
                    if candidate is None:
                        continue
                    key = plan_key(candidate)
                    if key in seen:
                        continue
                    seen.add(key)
                    variants.append((f"disperse_tid_{tid}_node_{node}_core_{target}_pos_{position}", candidate, "disperse"))
                    if len(variants) >= 160:
                        return variants
    return variants


def cache_delay_variants(view, base, cores, config):
    """Delay one repeated-tensor consumer behind work on a busy core.

    Moving a consumer to an idle core often leaves all COPY_IN queries at the
    same issue time, so the official FIFO cache correctly records misses. A
    bounded busy-core portfolio creates the timing state in which the first
    read can complete before a later read is issued. The official evaluator
    still decides whether the added work is worth keeping.
    """
    if cores < 2:
        return []
    variants = []
    seen = set()
    loads = _loads(view, base)
    groups, core_of = _group_maps(base)
    mapping = {int(node): int(group) for node, group in base["node_to_subgraph"].items()}
    busy_targets = sorted(range(cores), key=lambda core: (-loads.get(core, 0), core))
    for _potential, _structural, _size, tid, users, _user_cores in _shared_tensors(view, base, config)[:16]:
        consumer_groups = sorted(
            {mapping[int(node)] for node in users if int(node) in mapping},
            key=lambda group: (
                -sum(max(1, int(view["ops"][str(node)].get("cycles", 0))) for node in groups[group]),
                group,
            ),
        )
        for group in consumer_groups[:3]:
            source_core = core_of[group]
            for target in [core for core in busy_targets if core != source_core]:
                sequence_len = len(base["core_schedules"][target])
                positions = sorted({max(0, sequence_len - 1), sequence_len})
                for position in positions:
                    candidate = _move_group_core(view, base, group, target, position, cores)
                    if candidate is None:
                        continue
                    key = plan_key(candidate)
                    if key in seen:
                        continue
                    seen.add(key)
                    variants.append((f"cache_delay_group_tid_{tid}_group_{group}_core_{target}_pos_{position}", candidate, "cache_delay"))
                    if len(variants) >= 48:
                        return variants
        node_order = sorted(users, key=lambda node: (-int(view["ops"][str(node)].get("cycles", 0)), int(node)))[:3]
        for node in node_order:
            source_core = core_of[mapping[int(node)]]
            for target in [core for core in busy_targets if core != source_core]:
                sequence_len = len(base["core_schedules"][target])
                positions = sorted({max(0, sequence_len - 1), sequence_len})
                for position in positions:
                    candidate = _move_node(view, base, node, target, position, cores)
                    if candidate is None:
                        continue
                    key = plan_key(candidate)
                    if key in seen:
                        continue
                    seen.add(key)
                    variants.append((f"cache_delay_node_tid_{tid}_node_{node}_core_{target}_pos_{position}", candidate, "cache_delay"))
                    if len(variants) >= 48:
                        return variants
    return variants


def leader_skew_variants(view, base, cores, config):
    """Create FIFO-aware candidates with an explicit first-reader core.

    For a logical tensor read by several cores, one consumer core is treated
    as the leader.  Its consumer block is moved to the front of that core's
    sequence; the other consumer blocks are moved to the tail of their
    existing sequences.  The validator checks each edit and the event
    evaluator decides whether the resulting gap produces a cache hit.  The
    shared-tensor list is filtered by the current cache capacity, so a
    capacity perturbation changes the generated portfolio.
    """
    if cores < 2:
        return []
    mapping = {int(node): int(group) for node, group in base["node_to_subgraph"].items()}
    groups, core_of = _group_maps(base)
    variants = []
    seen = set()
    for _potential, _structural, _size, tid, users, user_cores in _shared_tensors(view, base, config)[:16]:
        consumer_groups = sorted({mapping[int(node)] for node in users if int(node) in mapping})
        if len(consumer_groups) < 2:
            continue
        # Try every consumer core as leader.  The deterministic order keeps
        # the portfolio reproducible while retaining alternatives when the
        # lowest-numbered core is not the best first reader.
        for leader in sorted(user_cores):
            candidate = base
            leader_groups = [group for group in consumer_groups if core_of[group] == leader]
            other_groups = [group for group in consumer_groups if core_of[group] != leader]
            for group in leader_groups:
                candidate = _move_group_position(view, candidate, group, 0) or candidate
            for group in other_groups:
                target = core_of[group]
                candidate = _move_group_position(view, candidate, group, len(candidate["core_schedules"][target])) or candidate
            key = plan_key(candidate)
            if key == plan_key(base) or key in seen:
                continue
            seen.add(key)
            variants.append((f"leader_skew_tid_{tid}_core_{leader}", candidate, "leader_skew"))
            if len(variants) >= 48:
                return variants
    return variants


def timing_variants(view, base, cores, config):
    """Move the groups serving repeated tensors to both ends of their cores."""
    variants = []
    seen = set()
    mapping = {int(node): int(group) for node, group in base["node_to_subgraph"].items()}
    for _potential, _structural, _size, tid, users, _user_cores in _shared_tensors(view, base, config)[:24]:
        groups = sorted({mapping[int(node)] for node in users if int(node) in mapping})
        for group in groups:
            core = next((index for index, sequence in enumerate(base["core_schedules"]) if group in sequence), None)
            if core is None or len(base["core_schedules"][core]) < 2:
                continue
            sequence_len = len(base["core_schedules"][core])
            for position, label in ((0, "front"), (sequence_len, "back")):
                candidate = _move_group_position(view, base, group, position)
                if candidate is None:
                    continue
                key = plan_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                variants.append((f"timing_tid_{tid}_group_{group}_{label}", candidate, "timing"))
    return variants[:96]


def event_timing_variants(view, base, cores, cache_events, config):
    """Generate C timing edits from the first official cache trace.

    The event trace identifies logical tensors that missed more than once and
    records the cumulative miss volume before each repeated miss.  We use that
    information to move the corresponding consumer block across an existing
    core order, preserving the graph and letting the official evaluator decide
    whether the new query ordering really produces a hit.
    """
    if cores < 2 or not cache_events:
        return []
    sizes = {int(tid): int(size) for tid, size in view["tensor_sizes"].items()}
    miss_counts = defaultdict(int)
    miss_bytes = defaultdict(int)
    first_miss = {}
    anchors = []
    for event in cache_events:
        if event.get("event") != "miss":
            continue
        tid = int(event.get("logical_tensor_id", event.get("tensor_id", -1)))
        size = int(event.get("size_bytes", sizes.get(tid, 0)))
        miss_counts[tid] += 1
        miss_bytes[tid] += size
        first_miss.setdefault(tid, int(event.get("time", 0)))
    for tid, count in miss_counts.items():
        consumer_map = view["tensor_consumers"]
        if count < 2 or (str(tid) not in consumer_map and tid not in consumer_map):
            continue
        anchors.append((count, miss_bytes[tid], first_miss.get(tid, 0), sizes.get(tid, 0), tid))
    anchors.sort(key=lambda item: (-item[1], -item[0], item[2], item[4]))

    mapping = {int(node): int(group) for node, group in base["node_to_subgraph"].items()}
    groups, core_of = _group_maps(base)
    variants = []
    seen = set()
    for count, cumulative, first_time, size, tid in anchors[:8]:
        users = [int(node) for node in consumer_map.get(str(tid), consumer_map.get(tid, ())) if int(node) in mapping]
        if len(users) < 2:
            continue
        user_groups = sorted({mapping[node] for node in users})
        # First try to create a real gap on the current core.  This is the
        # most local edit and is cheap to validate.
        for group in user_groups:
            core = core_of[group]
            sequence_len = len(base["core_schedules"][core])
            for position, label in ((0, "front"), (sequence_len, "back")):
                candidate = _move_group_position(view, base, group, position)
                if candidate is None:
                    continue
                key = plan_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                variants.append((
                    f"event_timing_tid_{tid}_miss_{count}_bytes_{cumulative}_{label}",
                    candidate,
                    "event_timing",
                ))
        # Then try placing a consumer block at the tail of a busy alternative
        # core.  The event anchor chooses the tensor; the evaluator verifies
        # the resulting COPY_IN order and cache state.
        loads = _loads(view, base)
        targets = sorted(range(cores), key=lambda core: (-loads.get(core, 0), core))
        for group in user_groups[:4]:
            source = core_of[group]
            for target in targets:
                if target == source:
                    continue
                candidate = _move_group_core(view, base, group, target, len(base["core_schedules"][target]), cores)
                if candidate is None:
                    continue
                key = plan_key(candidate)
                if key in seen:
                    continue
                seen.add(key)
                variants.append((
                    f"event_timing_tid_{tid}_miss_{count}_bytes_{cumulative}_core_{target}",
                    candidate,
                    "event_timing",
                ))
                if len(variants) >= 48:
                    return variants
    return variants


def choose_light(candidates):
    if not candidates:
        raise ValueError("no legal candidate")
    return candidates[0]
