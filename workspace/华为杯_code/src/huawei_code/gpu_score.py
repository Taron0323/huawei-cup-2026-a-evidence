"""Optional GPU batch scorer for candidate load vectors.

The official event evaluator is CPU Python.  This module only moves the
independent arithmetic used to rank candidate load vectors to Apple MPS when
it is available, and records the actual backend used.
"""

from __future__ import annotations

import time


def backend_info():
    try:
        import torch
    except Exception as exc:
        return {"available": False, "backend": "unavailable", "reason": repr(exc)}
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return {"available": True, "backend": "mps", "device": "Apple GPU"}
    return {"available": False, "backend": "cpu", "reason": "torch.backends.mps.is_available() is false"}


def rank_load_vectors(vectors):
    """Return max-load ranks and backend telemetry for an NxK numeric matrix."""
    import torch
    info = backend_info()
    device = torch.device("mps" if info["backend"] == "mps" else "cpu")
    started = time.perf_counter()
    # Apple MPS currently rejects float64 tensors; CPU keeps float64 for the
    # deterministic fallback while the ranking operation is integer-scale.
    dtype = torch.float32 if device.type == "mps" else torch.float64
    tensor = torch.as_tensor(vectors, dtype=dtype, device=device)
    maximum = torch.max(tensor, dim=1).values
    order = torch.argsort(maximum).detach().cpu().tolist()
    if device.type == "mps":
        torch.mps.synchronize()
    info.update({"rows": len(vectors), "columns": len(vectors[0]) if vectors else 0, "elapsed_seconds": time.perf_counter() - started, "used_for": "light candidate load ranking"})
    return order, info
