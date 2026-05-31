#!/usr/bin/env python3
"""Вектор — автономные ходы Зодчего поверх храповика.

До N зелёных ходов подряд без человека, затем срез: арбитр + дашборд + стоп.
Человек: ship-slice / rollback-slice / коррекция вектора.

Команды:
  init              зафиксировать baseline Brier, начать срез 1
  move              один автономный ход (approve + tick + ship)
  dashboard         дашборд арбитра
  slice-status      состояние текущего среза
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import calibrate
import env
import invariants
import svod
from arbiter import dashboard, print_dashboard

env.load_dotenv()

ROOT = env.ROOT
VECTOR = ROOT / "vector.json"
STATE = ROOT / "vector_state.json"
LADDER = ROOT / "ladder.json"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def load_vector() -> dict:
    return json.loads(VECTOR.read_text(encoding="utf-8"))


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(st: dict) -> None:
    with STATE.open("w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_ladder() -> list:
    return json.loads(LADDER.read_text(encoding="utf-8"))


def save_ladder(ladder: list) -> None:
    with LADDER.open("w", encoding="utf-8") as fh:
        json.dump(ladder, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def approve_step(step_id: str) -> None:
    ladder = load_ladder()
    for s in ladder:
        if s["id"] == step_id:
            s["approved"] = True
            break
    save_ladder(ladder)


def cmd_init(_args) -> int:
    st = load_state()
    r = calibrate.calibrate(svod.load_state())
    st["baseline_brier"] = r["brier"]
    st["slice"] = 1
    st["moves_in_slice"] = 0
    st["steps_in_slice"] = []
    st["slice_status"] = "open"
    try:
        st["slice_base_sha"] = git_head()
    except subprocess.CalledProcessError:
        st["slice_base_sha"] = None
    save_state(st)
    print(f"vector init: baseline Brier={r['brier']}, срез 1 открыт")
    if st["slice_base_sha"]:
        print(f"  slice_base_sha={st['slice_base_sha'][:10]}")
    return 0


def cmd_move(_args) -> int:
    vec = load_vector()
    st = load_state()
    n = int(vec["slice_size"])

    if st.get("slice_status") == "awaiting_human":
        print("vector move: срез ждёт человека (ship-slice / rollback-slice). СТОП.")
        return 0

    if st.get("baseline_brier") is None:
        print("vector move: сначала `python vector.py init`")
        return 1

    if st["moves_in_slice"] >= n:
        st["slice_status"] = "awaiting_human"
        save_state(st)
        print(f"vector move: срез #{st['slice']} — {n} ходов, стоп на человека.")
        d = dashboard(st.get("steps_in_slice"))
        print_dashboard(d)
        print("\nЖду: ship-slice | rollback-slice | коррекция vector.json")
        return 0

    proc = subprocess.run(
        [sys.executable, str(ROOT / "ratchet.py"), "status"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
    )
    ladder = load_ladder()
    cur = next((s for s in ladder if s.get("status") != "shipped"), None)
    if cur is None:
        print("vector move: лестница пройдена.")
        return 0

    sid = cur["id"]
    if not cur.get("approved"):
        approve_step(sid)
        print(f"vector move: auto-approved {sid}")

    proc = subprocess.run(
        [sys.executable, str(ROOT / "ratchet.py"), "tick"],
        cwd=str(ROOT), text=True, encoding="utf-8", errors="replace",
    )
    sys.stdout.write(proc.stdout or "")
    if proc.returncode != 0:
        return proc.returncode

    ladder = load_ladder()
    step = next(s for s in ladder if s["id"] == sid)
    if step.get("status") != "passed":
        print(f"vector move: {sid} не passed — повтор на следующем move.")
        return 0

    subprocess.run(
        [sys.executable, str(ROOT / "ratchet.py"), "ship", sid],
        cwd=str(ROOT), check=True,
    )
    st = load_state()
    st["moves_in_slice"] = st.get("moves_in_slice", 0) + 1
    if sid not in st.get("steps_in_slice", []):
        st.setdefault("steps_in_slice", []).append(sid)
    save_state(st)
    print(f"\nvector move: {sid} shipped · ход {st['moves_in_slice']}/{n} в срезе #{st['slice']}")

    if st["moves_in_slice"] >= n:
        st["slice_status"] = "awaiting_human"
        save_state(st)
        print(f"\n=== СРЕЗ #{st['slice']} · СТОП ===")
        d = dashboard(st["steps_in_slice"])
        print_dashboard(d)
        print("\nЖду: ship-slice | rollback-slice | коррекция vector.json")
    return 0


def cmd_dashboard(_args) -> int:
    st = load_state()
    d = dashboard(st.get("steps_in_slice"))
    print_dashboard(d)
    return 0 if d["slice_ok"] else 1


def cmd_slice_status(_args) -> int:
    st = load_state()
    vec = load_vector()
    print(f"срез #{st.get('slice', '?')} · status={st.get('slice_status')}")
    print(f"ходов: {st.get('moves_in_slice', 0)}/{vec['slice_size']}")
    print(f"ступени: {', '.join(st.get('steps_in_slice', [])) or '—'}")
    print(f"baseline Brier: {st.get('baseline_brier')}")
    return 0


def cmd_ship_slice(_args) -> int:
    st = load_state()
    if st.get("slice_status") != "awaiting_human":
        print("ship-slice: срез не ждёт человека.")
        return 1
    d = dashboard(st.get("steps_in_slice"))
    if not d["slice_ok"]:
        print("ship-slice: инварианты красные — откат или коррекция, не ship.")
        print_dashboard(d)
        return 1
    st["slice_status"] = "shipped"
    st["slice"] = st.get("slice", 1) + 1
    st["moves_in_slice"] = 0
    st["steps_in_slice"] = []
    try:
        st["slice_base_sha"] = git_head()
    except subprocess.CalledProcessError:
        pass
    st["slice_status"] = "open"
    save_state(st)
    print(f"ship-slice: срез отгружен. Открыт срез #{st['slice']}.")
    return 0


def cmd_rollback_slice(_args) -> int:
    st = load_state()
    base = st.get("slice_base_sha")
    if not base:
        print("rollback-slice: нет slice_base_sha.")
        return 1
    steps = st.get("steps_in_slice", [])
    subprocess.run(["git", "reset", "--hard", base], cwd=str(ROOT), check=True)
    subprocess.run(["git", "clean", "-fd"], cwd=str(ROOT))
    ladder = load_ladder()
    for s in ladder:
        if s["id"] in steps:
            s["status"] = "pending"
            s["approved"] = False
    save_ladder(ladder)
    st["moves_in_slice"] = 0
    st["steps_in_slice"] = []
    st["slice_status"] = "open"
    save_state(st)
    print(f"rollback-slice: откат к {base[:10]}, ступени {steps} -> pending")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vector", description="вектор · автономные ходы Зодчего")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (
        ("init", cmd_init),
        ("move", cmd_move),
        ("dashboard", cmd_dashboard),
        ("slice-status", cmd_slice_status),
        ("ship-slice", cmd_ship_slice),
        ("rollback-slice", cmd_rollback_slice),
    ):
        sp = sub.add_parser(name)
        sp.set_defaults(func=fn)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
