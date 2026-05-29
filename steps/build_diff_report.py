#!/usr/bin/env python3
"""Руки ступени R4: генерирует модуль diff_report.py.

Чертёж-codegen для R4. diff_report.py появляется только в фазе apply, поэтому
при красной приёмке `git clean` его снесёт, а чертёж останется.
"""

from pathlib import Path

DIFF_REPORT_PY = '''#!/usr/bin/env python3
"""diff_report — отчёт «что изменилось» между двумя переобучениями (learn).

Каждая команда СВОД пишет в history снимок уверенностей. Этот модуль берёт два
последних снимка с op=="learn" и показывает рябь: какие утверждения выросли,
какие упали. Так дискредитация источника даёт наглядный отчёт об изменениях.
"""

from __future__ import annotations

import sys

import svod

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def report(state: dict) -> list:
    """Список (claim, before, after, delta) между двумя последними learn-снимками."""
    learns = [h for h in state.get("history", []) if h.get("op") == "learn"]
    if len(learns) < 2:
        return []
    before, after = learns[-2]["snapshot"], learns[-1]["snapshot"]
    rows = []
    for key in set(before) | set(after):
        b, a = before.get(key, 0.0), after.get(key, 0.0)
        delta = round(a - b, 4)
        if abs(delta) > 1e-9:
            rows.append((key, b, a, delta))
    rows.sort(key=lambda r: abs(r[3]), reverse=True)
    return rows


def main() -> int:
    state = svod.load_state()
    rows = report(state)
    print(f"отчёт о ряби: изменилось утверждений {len(rows)}")
    for key, b, a, delta in rows:
        sign = "+" if delta > 0 else "-"
        print(f"  [{sign}] {b:.3f} -> {a:.3f}  {key}  ({delta:+.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

target = Path(__file__).resolve().parent.parent / "diff_report.py"
target.write_text(DIFF_REPORT_PY, encoding="utf-8")
print(f"build_diff_report: записан {target.name}")
