#!/usr/bin/env python3
"""Руки ступени R6: генерирует модуль calibrate.py.

Чертёж-codegen для R6. calibrate.py появляется только в фазе apply.
"""

from pathlib import Path

CALIBRATE_PY = '''#!/usr/bin/env python3
"""calibrate — оценка калибровки СВОД по отложенной разметке.

Берёт «золотой» набор (тема -> истинное утверждение) и сверяет с моделью:
  • accuracy — доля тем, где утверждение с макс. уверенностью совпало с истиной;
  • brier — средний (1 - уверенность_истины)^2 (чем ниже, тем лучше калибровка).
Это honest hold-out: разметка не участвует в обучении, только проверяет.
"""

from __future__ import annotations

import sys

import svod

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

GOLD = {
    "форма_земли": "шар",
    "вода_кипит_при": "100C",
    "вакцины": "безопасны",
}


def calibrate(state: dict, gold: dict = GOLD) -> dict:
    conf = svod.compute_confidences(state)
    hits = 0
    brier = 0.0
    n = 0
    rows = []
    for topic, truth in gold.items():
        claims = state["topics"].get(topic, {}).get("claims", {})
        if not claims:
            continue
        n += 1
        best = max(claims, key=lambda s: conf.get(svod.claim_key(topic, s), 0.0))
        c_true = conf.get(svod.claim_key(topic, truth), 0.0)
        hits += int(best == truth)
        brier += (1.0 - c_true) ** 2
        rows.append((topic, truth, best, round(c_true, 3)))
    return {
        "accuracy": (hits / n) if n else 0.0,
        "brier": round((brier / n) if n else 1.0, 4),
        "rows": rows,
    }


def main() -> int:
    state = svod.load_state()
    r = calibrate(state)
    print(f"калибровка: accuracy={r['accuracy']:.3f} brier={r['brier']}")
    for topic, truth, best, c_true in r["rows"]:
        mark = "ok" if best == truth else "MISS"
        print(f"  [{mark}] {topic}: истина={truth} модель={best} "
              f"уверенность_истины={c_true}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

target = Path(__file__).resolve().parent.parent / "calibrate.py"
target.write_text(CALIBRATE_PY, encoding="utf-8")
print(f"build_calibrate: записан {target.name}")
