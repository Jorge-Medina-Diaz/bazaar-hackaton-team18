"""Pure tactics of the t18 harness (docs/harness-spec.md §2.7). Each runner tactic proposes Intents; only the Gate
writes. pages plans the Needs; bench is an out-of-process Market Test recorder (bench_rec.py), not a tactic."""
from __future__ import annotations
