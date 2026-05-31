#!/usr/bin/env python3
"""Приёмка R12 — vector init, арбитр, стоп без человека на срезе."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import invariants
from arbiter import dashboard

# (б) нарушенный инвариант валит срез
vec = invariants.intent_cosine(
    "Храповик ходит по статьям, собирает утверждения, СВОД наполняется.",
    "совсем другая цель про погоду и космос",
)
assert vec < 0.8, f"тест конуса должен падать, cos={vec}"

bad = invariants.check_intent_cone(["FAKE"])
# пустой список шагов — ok; проверим с фейковым intent через monkeypatch state
state_file = ROOT / "vector_state.json"
backup = state_file.read_text(encoding="utf-8")
try:
    st = json.loads(backup)
    st["steps_in_slice"] = ["R9"]
    state_file.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ladder = json.loads((ROOT / "ladder.json").read_text(encoding="utf-8"))
    r9 = next(s for s in ladder if s["id"] == "R9")
    old_intent = r9["intent"]
    r9["intent"] = "совсем другая цель про погоду и космос"
    (ROOT / "ladder.json").write_text(
        json.dumps(ladder, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ok, detail, _ = invariants.check_intent_cone(["R9"])
    assert not ok, f"инвариант должен упасть: {detail}"
finally:
    state_file.write_text(backup, encoding="utf-8")
    ladder = json.loads((ROOT / "ladder.json").read_text(encoding="utf-8"))
    for s in ladder:
        if s["id"] == "R9":
            s["intent"] = old_intent
    (ROOT / "ladder.json").write_text(
        json.dumps(ladder, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# vector.py импортируется
import vector
assert hasattr(vector, "cmd_init")

print("R12 ok: арбитр валит дрейф интента; vector.py на месте")
