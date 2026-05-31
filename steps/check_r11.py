#!/usr/bin/env python3
"""Приёмка R11 — оффлайн: статьи -> candidates -> СВОД наполняется."""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import env
import article_walk
import news_ingest
import svod

env.ensure_data_dir()
state_path = Path(tempfile.mkdtemp()) / "svod_test.json"
os.environ["SVOD_STATE"] = str(state_path)

svod.save_state(svod.empty_state())

with tempfile.TemporaryDirectory() as td:
    cand = Path(td) / "candidates.jsonl"
    old_c = article_walk.CANDIDATES
    old_n = news_ingest.CANDIDATES
    article_walk.CANDIDATES = cand
    news_ingest.CANDIDATES = cand
    try:
        assert article_walk.main(["--fixtures"]) == 0
        assert news_ingest.main([]) == 0
    finally:
        article_walk.CANDIDATES = old_c
        news_ingest.CANDIDATES = old_n

state = svod.load_state()
assert len(state["observations"]) == 5, state["observations"]
topics = {o["topic"] for o in state["observations"]}
assert "удар_по_румынии" in topics, topics
svod.learn(state, 4)
svod.save_state(state)
conf = svod.compute_confidences(state)
assert any(c > 0 for c in conf.values()), conf
print(f"R11 ok: walk -> ingest -> learn, наблюдений={len(state['observations'])}")
