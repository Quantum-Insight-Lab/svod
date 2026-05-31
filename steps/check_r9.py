#!/usr/bin/env python3
"""Приёмка ступени R9 — оффлайн: data/, fixtures/, пути, dedup link в news_fetch."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import env
import news_fetch
import svod

env.load_dotenv()
dd = env.ensure_data_dir()
assert dd == env.data_dir(), "ensure_data_dir != data_dir"
assert "data" in dd.parts, f"каталог данных не data/: {dd}"

for name in ("sample_feed.txt", "echo_feed.txt"):
    p = env.fixtures_dir() / name
    assert p.is_file(), f"нет фикстуры {p}"

assert (ROOT / "collect.py").is_file(), "нет collect.py"

# svod по умолчанию пишет в data/
assert "data" in str(env.data_path("svod.json")), env.data_path("svod.json")

# known_links + dedup append_raw
with tempfile.NamedTemporaryFile(
    mode="w", suffix=".jsonl", delete=False, encoding="utf-8",
) as fh:
    fh.write('{"link":"https://example.org/a","title":"A"}\n')
    tmp = Path(fh.name)
try:
    seen = news_fetch.known_links(tmp)
    assert seen == {"https://example.org/a"}, seen
    old_raw = news_fetch.RAW
    news_fetch.RAW = tmp
    seen = news_fetch.known_links(tmp)
    n1 = news_fetch.append_raw(
        [{"link": "https://example.org/a", "title": "dup"}], seen)
    n2 = news_fetch.append_raw(
        [{"link": "https://example.org/b", "title": "new"}], seen)
    assert n1 == 0 and n2 == 1, f"dedup не сработал: {n1}, {n2}"
    news_fetch.RAW = old_raw
finally:
    tmp.unlink(missing_ok=True)

print("R9 ok: data/, fixtures/, пути env, dedup link в news_fetch")
