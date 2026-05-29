#!/usr/bin/env python3
"""Приёмка ступени R3: семантика должна бить лексический бейзлайн.

На размеченном мини-наборе пар:
  • лексический бейзлайн считает парафразой только идентичные (после
    нормализации) строки — на настоящих парафразах он ошибается;
  • семантический матчер ловит парафразы и не срабатывает на непохожих.
Проверяем, что точность семантики строго выше бейзлайна и не ниже 0.8.
Провал -> AssertionError -> ненулевой код -> красный tick.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dedup
import semantic

# пары-парафразы (по смыслу одно, но лексически различны)
POS = [
    ("Земля круглая", "Земля шарообразная"),
    ("планета имеет форму шара", "земля это шар"),
    ("вода кипит при 100 градусов", "вода кипение при 100 градус"),
]
# непохожие пары (разный смысл)
NEG = [
    ("Земля круглая", "вода кипит при 100"),
    ("вакцины безопасны", "земля шар"),
]


def lexical_eq(a: str, b: str) -> bool:
    return dedup.normalize(a) == dedup.normalize(b)


baseline = (sum(lexical_eq(a, b) for a, b in POS)
            + sum(not lexical_eq(a, b) for a, b in NEG))
sem = (sum(semantic.is_paraphrase(a, b) for a, b in POS)
       + sum(not semantic.is_paraphrase(a, b) for a, b in NEG))
total = len(POS) + len(NEG)

print(f"baseline {baseline}/{total}, semantic {sem}/{total}")
assert sem > baseline, f"семантика не бьёт бейзлайн: sem={sem} baseline={baseline}"
assert sem / total >= 0.8, f"низкая точность семантики: {sem}/{total}"
print(f"R3 ok: semantic {sem}/{total} > baseline {baseline}/{total}")
