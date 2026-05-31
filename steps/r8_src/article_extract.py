#!/usr/bin/env python3
"""article_extract — извлечь ВСЕ утверждения автора из тела статьи через Claude.

Слой СБОРА. LLM зовётся ТОЛЬКО здесь, по сети, по ключу из окружения, и
никогда — в приёмке. Чистые `build_prompt` и `parse_response` отделены от
сети и проверяются на замороженной фикстуре.

Принципы (решение по домену СВО — «свод всего знания»):
  • извлекаем ВСЕ фактические утверждения, ничего не фильтруя по теме;
  • нейросеть НЕ проверяет истинность — вес даст СВОД через надёжность изданий;
  • источник утверждения — ИЗДАНИЕ (article['source']); цитаты заносим как
    есть в форме «X заявил Y» отдельными утверждениями;
  • topic выдаётся каноническим снейк-кейсом, чтобы dedup схлопнул варианты.

Кандидаты дописываются в candidates.jsonl (тот же формат, что у news_extract,
approved=false), поэтому news_ingest заносит их без изменений.

Окружение:
    CLAUDE_API_KEY (или ANTHROPIC_API_KEY) — ключ
    ARTICLE_MODEL (или CLAUDE_MODEL)       — модель (по умолчанию claude-sonnet-4-6)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import env

env.load_dotenv()

import env

env.load_dotenv()

ROOT = Path(__file__).resolve().parent
ARTICLES = env.data_path("articles.jsonl")
CANDIDATES = env.data_path("candidates.jsonl")
CACHE = env.data_path("article_extract_cache.json")

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = (os.environ.get("ARTICLE_MODEL")
         or os.environ.get("CLAUDE_MODEL")
         or "claude-sonnet-4-6")
MAX_TOKENS = 4096
TIMEOUT = 120
try:
    ARTICLE_LIMIT = max(0, int(os.environ.get("ARTICLE_LIMIT", "0")))
except ValueError:
    ARTICLE_LIMIT = 0

SYSTEM = (
    "Ты — точный экстрактор утверждений из новостных и аналитических статей. Твоя задача — "
    "выписать ВСЕ фактические утверждения, которые делает текст: и собственные "
    "утверждения издания, и приписанные другим лицам в форме «X заявил, что Y». "
    "НИЧЕГО не проверяй на истинность, не оценивай, не комментируй и НЕ фильтруй "
    "по теме — бери всё, даже не относящееся к первичному запросу. Передавай смысл автора "
    "дословно, не додумывай. Отвечай ТОЛЬКО JSON-массивом без пояснений."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def article_key(link: str) -> str:
    return hashlib.sha1(link.encode("utf-8")).hexdigest()


def build_prompt(article: dict) -> str:
    """Собрать промпт по телу статьи (чистая функция)."""
    return (
        f"Издание: {article.get('source_name', article.get('source', ''))}\n"
        f"Заголовок: {article.get('title', '')}\n\n"
        f"Текст статьи:\n{article.get('text', '')}\n\n"
        "Выпиши ВСЕ фактические утверждения из текста. Для каждого верни объект "
        '{"topic": "<короткий_снейк_кейс>", "statement": "<утверждение одним '
        'предложением>"}. topic — обобщённый ключ темы в нижнем регистре через '
        "подчёркивания (например, удар_по_порту или потери_россии). "
        "Верни ТОЛЬКО JSON-массив таких объектов."
    )


def parse_response(text: str) -> list[dict]:
    """Достать JSON-массив утверждений из ответа модели (чистая функция)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("в ответе нет JSON-массива")
    arr = json.loads(s[start:end + 1])
    out = []
    for obj in arr:
        if not isinstance(obj, dict):
            continue
        topic = str(obj.get("topic", "")).strip()
        statement = str(obj.get("statement", "")).strip()
        if topic and statement:
            out.append({"topic": topic, "statement": statement})
    return out


def call_claude(prompt: str) -> str:
    key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("нет ключа: задай CLAUDE_API_KEY или ANTHROPIC_API_KEY")
    body = json.dumps({
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} model={MODEL}: {detail[:300]}") from exc
    parts = payload.get("content", [])
    return "".join(p.get("text", "") for p in parts if p.get("type") == "text")


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                     encoding="utf-8")


def load_articles() -> list[dict]:
    if not ARTICLES.exists():
        return []
    rows = []
    for line in ARTICLES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_candidates(rows: list[dict]) -> None:
    with CANDIDATES.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    env.ensure_data_dir()
    cache = load_cache()
    arts = [a for a in load_articles() if article_key(a["link"]) not in cache]
    if ARTICLE_LIMIT:
        arts = arts[:ARTICLE_LIMIT]
    if not arts:
        print("article_extract: новых статей нет (всё в кэше)")
        return 0
    print(f"article_extract: к обработке {len(arts)} статей моделью {MODEL}")
    produced = 0
    for i, art in enumerate(arts):
        try:
            extracted = parse_response(call_claude(build_prompt(art)))
        except Exception as exc:
            print(f"  [{art['source']}] {art['link'][:60]}: ОШИБКА {exc}")
            continue
        cache[article_key(art["link"])] = now_iso()
        out = []
        for e in extracted:
            out.append({
                "source": art["source"],
                "source_name": art.get("source_name", art["source"]),
                "topic": e["topic"],
                "statement": e["statement"],
                "title": art.get("title", ""),
                "link": art.get("link", ""),
                "published": art.get("published", ""),
                "extracted_at": now_iso(),
                "model": MODEL,
                "approved": False,
            })
        append_candidates(out)
        produced += len(out)
        print(f"  [{i + 1}/{len(arts)}] {art['source']:14s} +{len(out)} утверждений")
    save_cache(cache)
    print(f"article_extract: кандидатов +{produced} -> {CANDIDATES.name} "
          f"(approved=false, ждут человека)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
