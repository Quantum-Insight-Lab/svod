#!/usr/bin/env python3
"""Руки ступени R1: генерирует модуль harvest.py.

Это «codegen» храповика для ступени R1 — отдельный скрипт-чертёж, который
храповик запускает в фазе apply. Сам модуль harvest.py появляется только при
выполнении этого скрипта, поэтому при красной приёмке `git clean` его снесёт,
а чертёж (этот файл, закоммиченный как инфраструктура) останется.
"""

from pathlib import Path

HARVEST_PY = '''#!/usr/bin/env python3
"""harvest — сбор наблюдений из «сырого» источника в ядро СВОД.

Источник — текстовый фид строк вида:  [источник] тема = утверждение
(строки-комментарии начинаются с #). Каждая разобранная строка кладётся в
СВОД как наблюдение через публичный API svod.record_observation.
"""

from __future__ import annotations

import re
import sys

import svod

LINE = re.compile(r"^\\[(?P<src>[^\\]]+)\\]\\s*(?P<topic>[^=]+?)\\s*=\\s*(?P<stmt>.+)$")


def harvest(feed_path: str) -> int:
    """Прочитать фид, разобрать строки, записать наблюдения. Вернуть число."""
    state = svod.load_state()
    added = 0
    text = open(feed_path, encoding="utf-8").read()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE.match(line)
        if not m:
            continue
        svod.record_observation(
            state,
            m.group("src").strip(),
            m.group("topic").strip(),
            m.group("stmt").strip(),
        )
        added += 1
    svod.save_state(state)
    print(f"harvest: +{added} наблюдений из {feed_path}")
    return added


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python harvest.py FEED")
        raise SystemExit(2)
    harvest(sys.argv[1])
'''

target = Path(__file__).resolve().parent.parent / "harvest.py"
target.write_text(HARVEST_PY, encoding="utf-8")
print(f"build_harvest: записан {target.name}")
