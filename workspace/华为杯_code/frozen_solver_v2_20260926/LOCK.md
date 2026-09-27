# Immutable Formal-Run Workspace

This directory is the read-only execution copy for the formal A/B/C matrix. It was validated against `source.sha256` immediately before locking. The source, tests, input data, official evaluator, and Final Idea must not be edited while `results/final_main_clean_v05_20260926` is running. Only the `results/` directory is writable.

Frozen source hashes are the v2 values recorded in `source.sha256`; every child manifest must repeat them. Any hash drift or missing manifest is grounds for superseding the run.
