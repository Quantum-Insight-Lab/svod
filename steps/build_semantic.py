#!/usr/bin/env python3
"""Руки ступени R3: генерирует модуль semantic.py.

Чертёж-codegen для R3. semantic.py появляется только при запуске этого скрипта
в фазе apply, поэтому при красной приёмке `git clean` его снесёт, а чертёж
останется как инфраструктура.

Стек — только stdlib, без ML-модели: семантическое сопоставление сделано
эвристикой (нормализация + словарь синонимов + токены Жаккара + difflib для
склонений). Цель ступени — бить чисто лексический бейзлайн на парафразах.
"""

from pathlib import Path

SEMANTIC_PY = '''#!/usr/bin/env python3
"""semantic — сопоставление утверждений-парафразов без внешней модели.

Лексический бейзлайн считает равными только идентичные (после нормализации)
строки. Семантический матчер ловит парафразы: приводит синонимы к общему
корню, сравнивает множества значимых токенов (Жаккар) и под склонения
подстраховывается посимвольным сходством difflib.
"""

from __future__ import annotations

import difflib
import re

import dedup

# мини стоп-слова: служебные слова не несут смысла для сопоставления
STOP = {
    "и", "в", "на", "с", "по", "а", "от", "до", "при", "за", "это",
    "есть", "имеет", "форму", "форма", "у", "о",
}

# мини-словарь синонимов: разные слова -> общий корень (демо-набор)
SYN = {
    "круглый": "шар", "круглая": "шар", "круглое": "шар",
    "шарообразный": "шар", "шарообразная": "шар", "шара": "шар",
    "сфера": "шар", "сферическая": "шар", "сферический": "шар",
    "планета": "земля",
    "кипит": "кипение", "закипает": "кипение",
    "градусов": "градус", "градуса": "градус",
    "безопасный": "безопасны", "безопасна": "безопасны",
}

THRESHOLD = 0.5


def tokens(text: str) -> list:
    """Значимые токены утверждения: нормализация, отсев стоп-слов, синонимы."""
    base = dedup.normalize(text)
    out = []
    for tok in re.split(r"\\s+", base):
        if not tok or tok in STOP:
            continue
        out.append(SYN.get(tok, tok))
    return out


def similar(a: str, b: str) -> float:
    """Оценка сходства [0..1]: max(Жаккар по токенам, посимвольный difflib)."""
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    jacc = len(ta & tb) / len(ta | tb)
    seq = difflib.SequenceMatcher(
        None, " ".join(sorted(ta)), " ".join(sorted(tb))
    ).ratio()
    return max(jacc, seq)


def is_paraphrase(a: str, b: str, thr: float = THRESHOLD) -> bool:
    return similar(a, b) >= thr
'''

target = Path(__file__).resolve().parent.parent / "semantic.py"
target.write_text(SEMANTIC_PY, encoding="utf-8")
print(f"build_semantic: записан {target.name}")
