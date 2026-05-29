#!/usr/bin/env python3
"""Приёмка ступени R6: калибровка ниже порога ошибки.

На отложенной разметке после seed+learn модель обязана уверенно угадывать
консенсусные истины. Требуем accuracy >= 0.75 и Brier-ошибку < 0.3.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import calibrate

import svod

state = svod.load_state()
r = calibrate.calibrate(state)

print(f"accuracy={r['accuracy']:.3f} brier={r['brier']}")
assert r["accuracy"] >= 0.75, f"низкая точность: {r['accuracy']}"
assert r["brier"] < 0.3, f"плохая калибровка (Brier): {r['brier']}"
print(f"R6 ok: accuracy={r['accuracy']:.3f}, brier={r['brier']}")
