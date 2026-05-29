#!/usr/bin/env python3
"""Приёмка ступени R4: отчёт о ряби верно отражает дискредитацию.

Сценарий: после первого learn консенсус «шар» высок. Затем вбрасываются
сторонники «плоская» и идёт второй learn. Отчёт между двумя learn обязан
показать: «плоская» выросла (delta>0), «шар» упала (delta<0).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import diff_report
import svod

state = svod.load_state()
rows = diff_report.report(state)
assert rows, "отчёт пуст — недостаточно learn-снимков"

delta = {key: d for key, _, _, d in rows}
up = [k for k, v in delta.items() if "плоская" in k and v > 0]
down = [k for k, v in delta.items() if "шар" in k and v < 0]
assert up, f"«плоская» не выросла: {delta}"
assert down, f"«шар» не упал: {delta}"

shown = {k: round(v, 3) for k, v in delta.items() if "форма" in k}
print(f"R4 ok: рябь зафиксирована {shown}")
