# 人工智能工具辅助编程声明：本程序及代码在人工智能工具辅助下完成。
# 工具名称：OpenAI Codex；版本/型号：GPT-6 系列（准确会话型号以平台记录为准）；
# 开发机构：OpenAI；版本发布日期：以实际平台记录为准。
# 队员已对算法、参数、输入输出和官方评估结果进行人工核对，并保留后处理记录。

"""Independent checks for fresh plans and official result summaries."""

from __future__ import annotations

from .plan import validate_plan


def check_result(view, plan, result, cores):
    validate_plan(view, plan, cores)
    movement = result.get("data_movement_bytes", {})
    required = ("scheduled_copy_bytes", "original_graph_copy_bytes", "added_copy_bytes")
    missing = [key for key in required if key not in movement]
    if missing:
        raise ValueError(f"official result missing movement fields: {missing}")
    if int(result.get("makespan", -1)) < 0:
        raise ValueError("makespan must be nonnegative")
    if int(movement["scheduled_copy_bytes"]) - int(movement["original_graph_copy_bytes"]) < 0:
        raise ValueError("scheduled copy bytes below original graph bytes")
    cache = result.get("cache_stats") or {}
    if cache:
        hit, miss = int(cache.get("hit_bytes", 0)), int(cache.get("miss_bytes", 0))
        expected = hit / (hit + miss) if hit + miss else 0.0
        if abs(float(cache.get("hit_rate", 0.0)) - expected) > 1e-12:
            raise ValueError("cache byte hit rate mismatch")
    return {"status": "AI_VERIFIED", "makespan": result["makespan"], "added_copy_bytes": movement["added_copy_bytes"], "cache_hit_rate": cache.get("hit_rate", 0.0)}
