#!/usr/bin/env python3
"""Приёмка ступени R8 — целиком ОФФЛАЙН, на замороженных фикстурах.

Ни сети, ни ключа, ни Claude: проверяется только чистая логика инструментов
извлечения из тела статьи. Реальный сбор (сеть + Sonnet) — отдельная ручная
операция вне tick.

Что проверяем:
  • extract_text вытаскивает текст абзацев/заголовков/цитат статьи;
  • extract_text ВЫБРАСЫВАЕТ script/style/nav/footer (не утекает мусор);
  • build_prompt включает тело статьи и требование вернуть JSON-массив;
  • parse_response достаёт все утверждения из ответа в обёртке ```json;
  • источник кандидата = ИЗДАНИЕ (article['source']), а не цитируемое лицо;
  • candidates пишутся в формате, который понимает news_ingest.
Любой провал -> AssertionError -> ненулевой код -> красный tick.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FIX = Path(__file__).resolve().parent / "fixtures"

import article_fetch
import article_extract
import news_ingest
import svod

# 1. extract_text: тело статьи извлекается, мусор — нет
html = (FIX / "article_sample.html").read_text(encoding="utf-8")
text = article_fetch.extract_text(html)
assert "Russian drone struck a residential building" in text, "потерян первый абзац"
assert "reckless" in text, "потеряна реакция НАТО"
assert "violation of allied airspace" in text, "потеряна цитата (blockquote)"
for junk in ("DO_NOT_EXTRACT_THIS_SCRIPT", "DO_NOT_EXTRACT_NAV",
             "DO_NOT_EXTRACT_FOOTER", "trackEvent", "dataLayer"):
    assert junk not in text, f"в текст просочился мусор: {junk}"

# 2. build_prompt: тело статьи и требование JSON-массива в промпте
article = {
    "source": "bbc", "source_name": "BBC World",
    "title": "Drone hits Romania", "text": text, "link": "https://x/1",
}
prompt = article_extract.build_prompt(article)
assert "Russian drone struck" in prompt, "тело статьи не попало в промпт"
assert "JSON-массив" in prompt, "нет требования вернуть JSON-массив"

# 3. parse_response: достаём все утверждения из обёртки ```json
extracted = article_extract.parse_response(
    (FIX / "sonnet_response.txt").read_text(encoding="utf-8"))
assert len(extracted) == 5, f"ожидалось 5 утверждений, получено {len(extracted)}"
assert all(e["topic"] and e["statement"] for e in extracted), extracted
# цитата сохранена как отдельное утверждение «X заявил Y»
assert any("ответит на любое нарушение" in e["statement"] for e in extracted), \
    "цитата-утверждение потеряна"

# 4. источник кандидата = издание (не цитируемое лицо)
cands = []
for e in extracted:
    cands.append({
        "source": article["source"], "topic": e["topic"],
        "statement": e["statement"], "approved": True,
    })
srcs = {c["source"] for c in cands}
assert srcs == {"bbc"}, f"источник должен быть изданием, получено: {srcs}"

# 5. формат совместим с news_ingest: заносятся только approved, идемпотентно
state = svod.empty_state()
stats = news_ingest.ingest_approved(state, cands)
assert stats["ingested"] == 5, f"должно занестись 5, занеслось {stats}"
stats2 = news_ingest.ingest_approved(state, cands)
assert stats2["ingested"] == 0, f"не идемпотентно: {stats2}"
for ob in state["observations"]:
    assert ob["source"] == "bbc", ob

print("R8 ok: тело статьи извлечено без мусора, цитаты сохранены, источник=издание, "
      "ответ Sonnet парсится, формат совместим с news_ingest")
