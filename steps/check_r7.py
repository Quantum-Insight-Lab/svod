#!/usr/bin/env python3
"""Приёмка ступени R7 — целиком ОФФЛАЙН, на замороженных фикстурах.

Ни сети, ни ключа, ни Claude: проверяется только чистая логика инструментов
сбора, поэтому приёмка детерминирована и воспроизводима. Реальный сбор
(сеть + LLM) — отдельная ручная операция вне tick.

Что проверяем:
  • parse_rss разбирает RSS 2.0 и Atom (заголовки, ссылки, даты);
  • белый список блокирует хост вне sources_svo.json;
  • build_prompt включает заголовки с индексами;
  • parse_response достаёт кандидатов из ответа в обёртке ```json;
  • ingest_approved заносит ТОЛЬКО approved=true, идемпотентно, с провенансом.
Любой провал -> AssertionError -> ненулевой код -> красный tick.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).resolve().parent / "fixtures"

import svod
import news_fetch
import news_extract
import news_ingest

# 1. parse_rss: RSS 2.0
rss_items = news_fetch.parse_rss((FIX / "rss_sample.xml").read_text(encoding="utf-8"))
assert len(rss_items) == 2, f"ожидалось 2 item, получено {len(rss_items)}"
assert rss_items[0]["title"].startswith("Russia and Ukraine"), rss_items[0]
assert rss_items[0]["link"] == "https://example.org/news/1", rss_items[0]
assert rss_items[1]["published"], "нет даты у второго item"

# 1b. parse_rss: Atom (ссылка в атрибуте href)
atom_items = news_fetch.parse_rss((FIX / "atom_sample.xml").read_text(encoding="utf-8"))
assert len(atom_items) == 1, f"ожидался 1 entry, получено {len(atom_items)}"
assert atom_items[0]["link"] == "https://example.org/atom/1", atom_items[0]

# 2. белый список: хост вне списка отбивается ДО сети
blocked = False
try:
    news_fetch.fetch_source({"id": "evil", "rss": "https://evil.example/x"}, set())
except PermissionError:
    blocked = True
assert blocked, "белый список не сработал: чужой хост не отбит"

# 3. build_prompt: заголовки с индексами попадают в промпт
prompt = news_extract.build_prompt([
    {"title": "Headline A"}, {"title": "Headline B"},
])
assert "0. Headline A" in prompt and "1. Headline B" in prompt, prompt

# 4. parse_response: достаём массив из обёртки ```json
extracted = news_extract.parse_response((FIX / "claude_response.txt").read_text(encoding="utf-8"))
assert len(extracted) == 2, f"ожидалось 2 кандидата, получено {len(extracted)}"
assert all(e["topic"] and e["statement"] for e in extracted), extracted
assert extracted[0]["index"] == 0, extracted[0]

# 5. ingest_approved: только approved=true, с провенансом
cands = news_ingest.load_candidates(FIX / "candidates_sample.jsonl")
assert len(cands) == 3, f"в фикстуре ожидалось 3 кандидата, получено {len(cands)}"
state = svod.empty_state()
stats = news_ingest.ingest_approved(state, cands)
assert stats["ingested"] == 2, f"должно занестись 2 approved, занеслось {stats}"
srcs = {o["source"] for o in state["observations"]}
assert srcs == {"reuters", "bbc"}, f"провенанс не тот: {srcs}"
assert "rt" not in srcs, "неодобренный кандидат (rt) просочился в базу"

# 5b. идемпотентность: повторный ingest ничего не добавляет
stats2 = news_ingest.ingest_approved(state, cands)
assert stats2["ingested"] == 0 and stats2["skipped"] == 2, f"не идемпотентно: {stats2}"

print("R7 ok: RSS+Atom разобраны, белый список держит, ответ Claude парсится, "
      "ingest заносит только approved и идемпотентен")
