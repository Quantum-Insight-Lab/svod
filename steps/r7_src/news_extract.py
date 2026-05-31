#!/usr/bin/env python3
"""news_extract — извлечение (тема, утверждение) из заголовков через Claude.

Слой СБОРА. LLM зовётся ТОЛЬКО здесь, по сети, по ключу из окружения, и
никогда — в приёмке. Чистые функции `build_prompt` и `parse_response`
отделены от сети, поэтому разбор ответа проверяется на замороженной фикстуре.

Кандидаты пишутся в candidates.jsonl с провенансом и approved=false.
Человек проставляет approved=true (вручную или через news_approve), и только
после этого news_ingest заносит их в базу. Кэш по SHA-1 заголовка не даёт
платить за один и тот же заголовок дважды.

Окружение:
    CLAUDE_API_KEY (или ANTHROPIC_API_KEY) — ключ
    CLAUDE_MODEL   — модель (по умолчанию claude-haiku-4-5-20251001)
Параметры: BATCH=10 заголовков на вызов. EXTRACT_LIMIT=0 (по умолчанию) — весь
некэшированный raw.jsonl за один прогон; положительное число — потолок.
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
RAW = env.data_path("raw.jsonl")
CANDIDATES = env.data_path("candidates.jsonl")
CACHE = env.data_path("extract_cache.json")

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
BATCH = 10
try:
    EXTRACT_LIMIT = max(0, int(os.environ.get("EXTRACT_LIMIT", "0")))
except ValueError:
    EXTRACT_LIMIT = 0
TIMEOUT = 60

SYSTEM = (
    "Ты извлекаешь из новостных заголовков о войне России против Украины "
    "проверяемые фактические утверждения. Для каждого заголовка верни тему "
    "(короткий снейк-кейс ключ, например 'контроль_над_бахмутом') и "
    "утверждение (что именно заявлено). Игнорируй мнения и оценки. "
    "Отвечай ТОЛЬКО JSON-массивом без пояснений."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def headline_key(source: str, title: str) -> str:
    return hashlib.sha1(f"{source}\n{title}".encode("utf-8")).hexdigest()


def build_prompt(headlines: list[dict]) -> str:
    """Собрать пользовательский промпт из батча заголовков (чистая функция)."""
    lines = [
        "Заголовки (по одному на строку, с индексом):",
        "",
    ]
    for i, h in enumerate(headlines):
        lines.append(f"{i}. {h['title']}")
    lines += [
        "",
        "Верни JSON-массив объектов вида "
        '{"index": <число>, "topic": "<снейк_кейс>", "statement": "<утверждение>"}.',
        "Только заголовки с проверяемым фактом. Если факта нет — пропусти индекс.",
    ]
    return "\n".join(lines)


def parse_response(text: str) -> list[dict]:
    """Достать JSON-массив из ответа модели (чистая функция).

    Терпимо относится к обёрткам ```json ... ``` и к тексту вокруг массива.
    """
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
            out.append({
                "index": obj.get("index"),
                "topic": topic,
                "statement": statement,
            })
    return out


def call_claude(prompt: str) -> str:
    key = os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("нет ключа: задай CLAUDE_API_KEY или ANTHROPIC_API_KEY")
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 1024,
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


def load_raw() -> list[dict]:
    if not RAW.exists():
        return []
    rows = []
    for line in RAW.read_text(encoding="utf-8").splitlines():
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
    raw = [r for r in load_raw() if headline_key(r["source"], r["title"]) not in cache]
    if EXTRACT_LIMIT:
        raw = raw[:EXTRACT_LIMIT]
    if not raw:
        print("news_extract: новых заголовков нет (всё в кэше)")
        return 0
    print(f"news_extract: к обработке {len(raw)} заголовков")
    produced = 0
    for start in range(0, len(raw), BATCH):
        batch = raw[start:start + BATCH]
        prompt = build_prompt(batch)
        try:
            extracted = parse_response(call_claude(prompt))
        except Exception as exc:
            print(f"  батч {start // BATCH}: ОШИБКА {exc}")
            continue
        by_index = {e["index"]: e for e in extracted if e.get("index") is not None}
        out = []
        for i, h in enumerate(batch):
            cache[headline_key(h["source"], h["title"])] = now_iso()
            e = by_index.get(i)
            if not e:
                continue
            out.append({
                "source": h["source"],
                "source_name": h.get("source_name", h["source"]),
                "topic": e["topic"],
                "statement": e["statement"],
                "title": h["title"],
                "link": h.get("link", ""),
                "published": h.get("published", ""),
                "extracted_at": now_iso(),
                "model": MODEL,
                "approved": False,
            })
        append_candidates(out)
        produced += len(out)
        print(f"  батч {start // BATCH}: заголовков {len(batch)} -> кандидатов {len(out)}")
    save_cache(cache)
    print(f"news_extract: кандидатов +{produced} -> {CANDIDATES.name} "
          f"(approved=false, ждут человека)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
