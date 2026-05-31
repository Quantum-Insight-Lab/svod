#!/usr/bin/env python3
"""article_walk — оффлайн проход по статьям: тела -> candidates (без сети).

Режим --fixtures: замороженные статьи и ответ Sonnet из steps/fixtures/.
Для реального сбора (сеть + LLM) — collect.py, вне приёмки.

    python article_walk.py --fixtures
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import env

env.load_dotenv()

ROOT = env.ROOT
FIX = ROOT / "steps" / "fixtures"
CANDIDATES = env.data_path("candidates.jsonl")

import article_extract


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_candidates(rows: list[dict], path: Path) -> None:
    env.ensure_data_dir()
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def walk_articles(articles: list[dict], response_text: str, approved: bool = True) -> list[dict]:
    extracted = article_extract.parse_response(response_text)
    out: list[dict] = []
    for article in articles:
        src = article["source"]
        for e in extracted:
            out.append({
                "source": src,
                "topic": e["topic"],
                "statement": e["statement"],
                "approved": approved,
                "title": article.get("title", ""),
                "link": article.get("link", ""),
            })
    return out


def fixtures_walk() -> list[dict]:
    articles = load_jsonl(FIX / "articles_walk.jsonl")
    response = (FIX / "sonnet_response.txt").read_text(encoding="utf-8")
    return walk_articles(articles, response, approved=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--fixtures" not in argv:
        print("article_walk: только --fixtures (оффлайн). Реальный сбор: collect.py")
        return 1
    cands = fixtures_walk()
    write_candidates(cands, CANDIDATES)
    print(f"article_walk: {len(cands)} кандидатов -> {CANDIDATES.name} (approved=true)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
