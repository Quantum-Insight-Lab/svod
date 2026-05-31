#!/usr/bin/env python3
"""news_ingest — занести ОДОБРЕННЫХ человеком кандидатов в базу СВОД.

Шлюз человека: в базу попадают только кандидаты с approved=true в
candidates.jsonl. Идемпотентно: повторный запуск не плодит дубли наблюдений
(дедуп по тройке source/topic/statement). Провенанс (источник, заголовок,
ссылка) сохраняется как наблюдение свода.

    python news_ingest.py            # из candidates.jsonl в базу svod
    python news_ingest.py --dry      # показать, что было бы занесено
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import svod

import env

env.load_dotenv()

ROOT = Path(__file__).resolve().parent
CANDIDATES = env.data_path("candidates.jsonl")


def load_candidates(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def existing_triples(state: dict) -> set[tuple]:
    return {
        (o["source"], o["topic"], o["statement"])
        for o in state["observations"]
    }


def ingest_approved(state: dict, candidates: list[dict]) -> dict:
    """Занести approved-кандидатов. Возвращает статистику ingested/skipped."""
    seen = existing_triples(state)
    ingested = 0
    skipped = 0
    for c in candidates:
        if not c.get("approved"):
            continue
        triple = (c["source"], c["topic"], c["statement"])
        if triple in seen:
            skipped += 1
            continue
        svod.record_observation(state, c["source"], c["topic"], c["statement"])
        seen.add(triple)
        ingested += 1
    return {"ingested": ingested, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dry = "--dry" in argv
    candidates = load_candidates(CANDIDATES)
    approved = [c for c in candidates if c.get("approved")]
    if not approved:
        print("news_ingest: одобренных кандидатов нет (approved=true)")
        return 0
    state = svod.load_state()
    stats = ingest_approved(state, candidates)
    if dry:
        print(f"news_ingest --dry: занеслось бы {stats['ingested']}, "
              f"пропуск (дубли) {stats['skipped']}")
        return 0
    svod.snapshot(state, "news_ingest",
                  f"+{stats['ingested']} наблюдений из новостей")
    svod.save_state(state)
    print(f"news_ingest: занесено {stats['ingested']}, "
          f"пропущено дублей {stats['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
