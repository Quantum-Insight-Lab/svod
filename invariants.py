#!/usr/bin/env python3
"""Инварианты вектора — контракт человека. Агент (Зодчий) этот файл НЕ редактирует.

Проверяются арбитром на каждом срезе. Срез зелёный только если ВСЕ держатся.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VECTOR_FILE = ROOT / "vector.json"
STATE_FILE = ROOT / "vector_state.json"
LADDER = ROOT / "ladder.json"

BRIER_MARGIN = 0.02
NETWORK_MARKERS = re.compile(
    r"anthropic|claude|openai|urllib\.request|requests\.|http://|https://|api\.",
    re.I,
)

_token_re = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+", re.UNICODE)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _token_re.findall(text) if len(t) > 2}


def intent_cosine(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / (len(ta) * len(tb)) ** 0.5


def baseline_brier() -> float:
    st = _load_json(STATE_FILE)
    b = st.get("baseline_brier")
    if b is None:
        raise RuntimeError("baseline_brier не задан: vector init")
    return float(b)


def check_calibration() -> tuple[bool, str, float | None]:
    import calibrate
    import svod

    r = calibrate.calibrate(svod.load_state())
    brier = float(r["brier"])
    limit = baseline_brier() + BRIER_MARGIN
    ok = brier <= limit
    return ok, f"Brier {brier:.4f} ≤ {limit:.4f} (baseline+{BRIER_MARGIN})", brier


def check_monotonicity() -> tuple[bool, str]:
    ladder = json.loads(LADDER.read_text(encoding="utf-8"))
    shipped = [s for s in ladder if s.get("status") == "shipped"]
    failed = []
    for step in shipped:
        for cmd in step.get("checks", []):
            proc = subprocess.run(
                cmd, shell=True, cwd=str(ROOT),
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env={**dict(__import__("os").environ),
                     "SVOD_STATE": str(ROOT / "data" / ".accept_state.json")},
            )
            if proc.returncode != 0:
                failed.append(f"{step['id']}: rc={proc.returncode}")
    if failed:
        return False, "сломанные shipped: " + "; ".join(failed[:3])
    return True, f"shipped checks зелёные ({len(shipped)} ступеней)"


def check_deterministic_acceptance() -> tuple[bool, str]:
    ladder = json.loads(LADDER.read_text(encoding="utf-8"))
    bad = []
    for step in ladder:
        if step.get("status") not in ("passed", "shipped", "pending"):
            continue
        for cmd in step.get("checks", []):
            if NETWORK_MARKERS.search(cmd):
                bad.append(f"{step['id']}: {cmd[:60]}")
    if bad:
        return False, "сеть/LLM в checks: " + bad[0]
    return True, "checks без сети и LLM"


def check_intent_cone(step_ids: list[str] | None = None) -> tuple[bool, str, float | None]:
    vec = _load_json(VECTOR_FILE)["text"]
    threshold = float(_load_json(VECTOR_FILE).get("intent_cone_threshold", 0.8))
    ladder = json.loads(LADDER.read_text(encoding="utf-8"))
    if step_ids:
        steps = [s for s in ladder if s["id"] in step_ids]
    else:
        st = _load_json(STATE_FILE)
        steps = [s for s in ladder if s["id"] in st.get("steps_in_slice", [])]
    if not steps:
        return True, "нет ступеней в срезе для проверки конуса", None
    scores = [intent_cosine(vec, s.get("intent", "")) for s in steps]
    worst = min(scores)
    ok = worst >= threshold
    return ok, f"min cos={worst:.3f} ≥ {threshold} ({len(steps)} ступеней)", worst


def check_complexity_budget() -> tuple[bool, str, int | None]:
    st = _load_json(STATE_FILE)
    budget = int(_load_json(VECTOR_FILE).get("loc_budget_per_slice", 800))
    base = st.get("slice_base_sha")
    if not base:
        return True, "slice_base_sha не задан — бюджет не считаем", 0
    proc = subprocess.run(
        ["git", "diff", "--numstat", base, "HEAD"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    loc = 0
    for line in (proc.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            loc += int(parts[0]) + int(parts[1])
    ok = loc <= budget
    deps = list((ROOT / "requirements.txt").glob("*")) if (ROOT / "requirements.txt").exists() else []
    new_deps = len(deps) > 0 and False  # нет requirements — новых зависимостей 0
    if (ROOT / "requirements.txt").exists():
        # новых внешних зависимостей = 0: файл не должен появиться в срезе
        proc2 = subprocess.run(
            ["git", "diff", "--name-only", base, "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        if "requirements.txt" in (proc2.stdout or ""):
            return False, "появился requirements.txt", loc
    return ok, f"LOC Δ={loc} ≤ {budget}, новых зависимостей=0", loc


def run_all(step_ids: list[str] | None = None) -> list[dict]:
    """Прогнать все инварианты. Возвращает список {id, ok, detail, value}."""
    results = []
    ok, detail, val = check_calibration()
    results.append({"id": "calibration", "ok": ok, "detail": detail, "value": val})
    ok, detail = check_monotonicity()
    results.append({"id": "monotonicity", "ok": ok, "detail": detail, "value": None})
    ok, detail = check_deterministic_acceptance()
    results.append({"id": "deterministic", "ok": ok, "detail": detail, "value": None})
    ok, detail, val = check_intent_cone(step_ids)
    results.append({"id": "intent_cone", "ok": ok, "detail": detail, "value": val})
    ok, detail, val = check_complexity_budget()
    results.append({"id": "complexity", "ok": ok, "detail": detail, "value": val})
    return results


def slice_ok(step_ids: list[str] | None = None) -> bool:
    return all(r["ok"] for r in run_all(step_ids))


if __name__ == "__main__":
    for r in run_all():
        mark = "OK" if r["ok"] else "FAIL"
        print(f"[{mark}] {r['id']}: {r['detail']}")
    raise SystemExit(0 if slice_ok() else 1)
