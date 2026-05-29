#!/usr/bin/env python3
"""Приёмка ступени R2: проверяет, что дедупликация схлопнула эхо.

Инварианты после dedup:
  • все ключи тем и утверждений уже в канонической форме (идемпотентность);
  • варианты написания «шар» слиты в один канон, за который голосует >= 3
    источника (раньше голоса были расщеплены по Шар/шар./ШАР);
  • уверенность канонического «шар» высокая (> 0.6).
Любой провал поднимает AssertionError -> ненулевой код возврата -> красный tick.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dedup
import svod

state = svod.load_state()

for topic, tdata in state["topics"].items():
    assert topic == dedup.normalize(topic), f"тема не нормализована: {topic!r}"
    for claim in tdata["claims"]:
        assert claim == dedup.normalize(claim), f"утверждение не нормализовано: {claim!r}"

nt = dedup.normalize("форма_земли")
srcs = {
    o["source"]
    for o in state["observations"]
    if o["topic"] == nt and o["statement"] == "шар"
}
assert len(srcs) >= 3, f"мало источников за «шар» после дедупа: {sorted(srcs)}"

conf = svod.compute_confidences(state)
cs = conf[svod.claim_key(nt, "шар")]
assert cs > 0.6, f"низкая уверенность «шар»: {cs}"

print(f"R2 ok: тема {nt!r}, источников за «шар»: {len(srcs)}, уверенность: {round(cs, 3)}")
