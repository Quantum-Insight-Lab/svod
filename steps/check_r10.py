#!/usr/bin/env python3
"""Приёмка R10 — article_walk на фикстурах, без сети."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import env
import article_walk

env.ensure_data_dir()
with tempfile.TemporaryDirectory() as td:
    cand = Path(td) / "candidates.jsonl"
    old = article_walk.CANDIDATES
    article_walk.CANDIDATES = cand
    try:
        rc = article_walk.main(["--fixtures"])
        assert rc == 0, rc
        rows = [json.loads(l) for l in cand.read_text(encoding="utf-8").splitlines() if l.strip()]
    finally:
        article_walk.CANDIDATES = old

assert len(rows) == 5, f"ожидалось 5 кандидатов, {len(rows)}"
assert all(r.get("approved") for r in rows), rows
assert {r["source"] for r in rows} == {"bbc"}, rows
print("R10 ok: article_walk --fixtures -> 5 approved кандидатов от bbc")
