#!/usr/bin/env python3
"""Приёмка ступени R5: HTML — функция живой базы.

Проверяем, что страница строится из состояния и содержит тему/утверждение с
провенансом, а при смене надёжности источников (без правок кода рендера) HTML
меняется — то есть реагирует на живую базу.
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render
import svod

state = svod.load_state()
h1 = render.render(state)
assert "форма_земли" in h1, "в HTML нет темы форма_земли"
assert "шар" in h1, "в HTML нет утверждения шар"

# смена надёжности без единой правки кода рендера -> другой HTML
s2 = copy.deepcopy(state)
for name in ("alice", "bob", "dave", "reuters", "nasa"):
    if name in s2["sources"]:
        s2["sources"][name]["reliability"] = 0.05
h2 = render.render(s2)
assert h1 != h2, "HTML не реагирует на смену надёжности"

print(f"R5 ok: HTML реагирует на состояние (длина {len(h1)} символов)")
