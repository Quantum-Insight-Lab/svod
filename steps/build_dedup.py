#!/usr/bin/env python3
"""Руки ступени R2: генерирует модуль dedup.py.

Чертёж-codegen для ступени R2. Сам модуль dedup.py появляется только при
запуске этого скрипта в фазе apply, поэтому при красной приёмке `git clean`
его снесёт, а чертёж (этот файл) останется как инфраструктура.
"""

from pathlib import Path

DEDUP_PY = '''#!/usr/bin/env python3
"""dedup — нормализация и схлопывание near-duplicate в базе СВОД.

Разные написания одной мысли (регистр, пунктуация, подчёркивания/пробелы)
приводятся к канонической форме, после чего темы и утверждения пересобираются
по каноническим ключам. Это не даёт «эху» — повтору одной мысли разным
написанием — плодить сущности и накручивать уверенность.
"""

from __future__ import annotations

import re

import svod


def normalize(text: str) -> str:
    """Канонизировать строку: регистр, пробелы/подчёркивания, хвостовая пунктуация."""
    t = text.strip().lower()
    t = t.replace("\\u00b0", "")            # градусы
    t = re.sub(r"[_\\s]+", " ", t)            # подчёркивания и пробелы -> один пробел
    t = t.strip(" .!?,;:")                   # обрамляющая пунктуация
    return t


def dedup_state(state: dict) -> dict:
    """Пересобрать темы и наблюдения по нормализованным ключам.

    Возвращает статистику: сколько тем/утверждений было и стало.
    Источники и их надёжности не трогаются.
    """
    before_topics = len(state["topics"])
    before_claims = sum(len(t["claims"]) for t in state["topics"].values())

    new_topics: dict = {}
    new_obs: list = []
    for ob in state["observations"]:
        ct = normalize(ob["topic"])
        cs = normalize(ob["statement"])
        new_obs.append({**ob, "topic": ct, "statement": cs})
        claims = new_topics.setdefault(ct, {"claims": {}})["claims"]
        claims.setdefault(cs, {"added": ob.get("time", "")})

    state["topics"] = new_topics
    state["observations"] = new_obs

    after_topics = len(new_topics)
    after_claims = sum(len(t["claims"]) for t in new_topics.values())
    return {
        "topics_before": before_topics, "topics_after": after_topics,
        "claims_before": before_claims, "claims_after": after_claims,
    }


def main() -> int:
    state = svod.load_state()
    stats = dedup_state(state)
    svod.save_state(state)
    print(
        "dedup: темы {topics_before}->{topics_after}, "
        "утверждения {claims_before}->{claims_after}".format(**stats)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

target = Path(__file__).resolve().parent.parent / "dedup.py"
target.write_text(DEDUP_PY, encoding="utf-8")
print(f"build_dedup: записан {target.name}")
