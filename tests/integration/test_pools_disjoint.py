"""SC-005 — train/eval pools disjoint + realized 70/30 split within ±5pp.

Tests the pure deterministic partition function (no download needed). Disjointness
is by construction: each problem id maps to exactly one pool.
"""
from __future__ import annotations

from benchmark_loader.load import DEFAULT_DATASETS, assign_pool

_IDS = [f"gsm8k-train-{i}" for i in range(5000)]


def test_each_id_maps_to_exactly_one_pool():
    for pid in _IDS[:200]:
        assert assign_pool(pid) in ("training", "evaluation")


def test_deterministic():
    assert assign_pool("math-train-42") == assign_pool("math-train-42")


def test_hf_paths_are_namespaced():
    # current huggingface_hub rejects bare ids (e.g. 'gsm8k'); require 'namespace/name'.
    for spec in DEFAULT_DATASETS:
        assert "/" in spec["hf_path"], spec["hf_path"]


def test_split_ratio_within_band():
    train = sum(1 for pid in _IDS if assign_pool(pid) == "training")
    share = train / len(_IDS)
    assert 0.65 <= share <= 0.75, share
