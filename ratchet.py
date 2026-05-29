#!/usr/bin/env python3
"""Храповик — ограниченный цикл сборки поверх ядра СВОД.

Растит проект по одной ступени за раз. Неподделываемая приёмка (вердикт
только из кодов возврата реальных подпроцессов), обязательный человеческий
шлюз между ступенями (passed -> shipped и одобрение следующей делает только
человек). Только стандартная библиотека; git вызывается через subprocess.

Команды:
  tick   [--ladder F]   один удар: максимум одна попытка одной ступени
  ship   ID [--ladder F]  человек: пометить passed-ступень как shipped
  status [--ladder F]   показать состояние лестницы (read-only)
  verify ID [--ladder F]  заново прогнать checks ступени и сверить с журналом

Гарантии (зашиты в код):
  • Песочница: все подпроцессы исполняются с cwd = каталог проекта; за его
    пределы храповик не выходит; сетевых вызовов в коде нет.
  • Версионный контроль: перед изменением дерево приводится к чистому
    (снапшот-коммит при необходимости); любое изменение либо коммитится,
    либо откатывается (reset --hard + clean). Репозиторий не остаётся сломан.
  • Ограниченность: нет цикла по ступеням; один tick = одна ступень.
  • Никакого самозачёта: вердикт выводится только из захваченного вывода.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

ROOT = Path(__file__).resolve().parent
LADDER_DEFAULT = ROOT / "ladder.json"
JOURNAL = ROOT / "journal.jsonl"

# инлайн-личность для коммитов храповика: НЕ трогаем глобальный git config
GIT_ID = ["-c", "user.name=ratchet", "-c", "user.email=ratchet@local"]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Песочница: всякий подпроцесс исполняется внутри каталога проекта
# --------------------------------------------------------------------------- #
def run_shell(cmd: str) -> dict:
    """Выполнить команду приёмки как реальный подпроцесс, захватить вывод."""
    proc = subprocess.run(
        cmd, shell=True, cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return {"cmd": cmd, "rc": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args], cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -> {proc.returncode}\n{proc.stderr}")
    return proc


def ensure_repo() -> None:
    proc = git("rev-parse", "--is-inside-work-tree", check=False)
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        raise SystemExit("храповик: это не git-репозиторий. Сначала git init.")


def is_dirty() -> bool:
    return bool(git("status", "--porcelain").stdout.strip())


def ensure_clean() -> None:
    """Перед любым изменением дерево должно быть чистым: иначе снапшот-коммит."""
    if is_dirty():
        git("add", "-A")
        git(*GIT_ID, "commit", "-m", "ratchet: snapshot")


def head_sha() -> str:
    return git("rev-parse", "HEAD").stdout.strip()


# --------------------------------------------------------------------------- #
# Лестница и журнал
# --------------------------------------------------------------------------- #
def load_ladder(path: Path) -> list:
    if not path.exists():
        raise SystemExit(f"храповик: лестница не найдена: {path}")
    with path.open("r", encoding="utf-8") as fh:
        ladder = json.load(fh)
    if not isinstance(ladder, list):
        raise SystemExit("храповик: ladder.json должен быть списком ступеней.")
    return ladder


def save_ladder_status(path: Path, step_id: str, status: str) -> None:
    """Меняем ТОЛЬКО поле status указанной ступени; порядок и содержание не трогаем."""
    ladder = load_ladder(path)
    for step in ladder:
        if step["id"] == step_id:
            step["status"] = status
            break
    with path.open("w", encoding="utf-8") as fh:
        json.dump(ladder, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def journal_append(entry: dict) -> None:
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def journal_entries(step_id: str) -> list:
    if not JOURNAL.exists():
        return []
    out = []
    for line in JOURNAL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        if e.get("step") == step_id:
            out.append(e)
    return out


def first_unshipped(ladder: list):
    for step in ladder:
        if step.get("status") != "shipped":
            return step
    return None


# --------------------------------------------------------------------------- #
# Приёмка (Арбитр): вердикт ТОЛЬКО из кодов возврата
# --------------------------------------------------------------------------- #
def run_phase(commands: list, phase: str) -> tuple[list, bool]:
    """Прогнать список команд. Зелено фазы — если ВСЕ вернули 0."""
    results = []
    ok = True
    for cmd in commands:
        r = run_shell(cmd)
        r["phase"] = phase
        results.append(r)
        if r["rc"] != 0:
            ok = False
            break  # дальше не идём: фаза уже красная
    return results, ok


def print_outputs(outputs: list) -> None:
    for r in outputs:
        print(f"  [{r['phase']}] $ {r['cmd']}")
        print(f"    rc={r['rc']}")
        if r["stdout"].strip():
            for ln in r["stdout"].rstrip().splitlines():
                print(f"    out| {ln}")
        if r["stderr"].strip():
            for ln in r["stderr"].rstrip().splitlines():
                print(f"    err| {ln}")


# --------------------------------------------------------------------------- #
# tick — один удар
# --------------------------------------------------------------------------- #
def cmd_tick(args) -> int:
    ladder_path = Path(args.ladder)
    ensure_repo()
    ensure_clean()

    ladder = load_ladder(ladder_path)
    step = first_unshipped(ladder)

    # 1) лестница пройдена
    if step is None:
        print("храповик: все ступени отгружены. Лестница пройдена — двигаться некуда.")
        return 0

    sid = step["id"]

    # человеческий шлюз №1: пройденная, но не отгруженная ступень блокирует
    if step.get("status") == "passed":
        print(f"храповик: ступень {sid} уже passed. Нужен человек: "
              f"`python ratchet.py ship {sid}` и/или approved=true у следующей.")
        return 0

    # 2) человеческий шлюз №2: без одобрения ничего не делаем
    if not step.get("approved", False):
        print(f"жду одобрения ступени {sid} — «{step.get('title', '')}». "
              f"Поставь approved=true (это делает только человек).")
        return 0

    base = head_sha()
    print(f"храповик tick: ступень {sid} — «{step.get('title', '')}»")
    print(f"  намерение: {step.get('intent', '')}")
    print(f"  база: {base[:10]}")

    # 3) минимальное изменение под intent (декларативный codegen ступени)
    outputs, ok = run_phase(step.get("apply", []), "apply")

    # 4) приёмка ступени
    if ok:
        check_out, ok = run_phase(step.get("checks", []), "check")
        outputs += check_out

    verdict = "green" if ok else "red"

    if ok:
        # 5) ЗЕЛЕНО: фиксируем изменение и статус, журналим, ОСТАНАВЛИВАЕМСЯ
        save_ladder_status(ladder_path, sid, "passed")
        git("add", "-A")
        git(*GIT_ID, "commit", "-m", f"ratchet: {sid} passed")
        sha = head_sha()
        journal_append({
            "time": now_iso(), "step": sid, "sha": sha,
            "verdict": verdict, "checks": outputs,
        })
        print("\n--- ЗЕЛЕНО ---")
        print_outputs(outputs)
        print(f"\nкоммит {sha[:10]} «ratchet: {sid} passed»; статус -> passed.")
        print(f"СТОП. Следующую ступень храповик сам не берёт — нужен человек.")
        return 0

    # 6) КРАСНО: откат к последнему коммиту, журналим причину, СТОП
    git(*GIT_ID, "reset", "--hard", base)
    git("clean", "-fd")  # снести только что созданные неотслеживаемые файлы (.gitignore сохраняется)
    journal_append({
        "time": now_iso(), "step": sid, "sha": "откат",
        "verdict": verdict, "checks": outputs,
    })
    print("\n--- КРАСНО ---")
    print_outputs(outputs)
    print(f"\nоткат к {base[:10]}; рабочее дерево чистое, репозиторий рабочий.")
    print(f"статус ступени {sid} не меняется (остаётся pending). СТОП.")
    return 0


# --------------------------------------------------------------------------- #
# ship — человеческое действие: passed -> shipped
# --------------------------------------------------------------------------- #
def cmd_ship(args) -> int:
    ladder_path = Path(args.ladder)
    ensure_repo()
    ladder = load_ladder(ladder_path)
    step = next((s for s in ladder if s["id"] == args.id), None)
    if step is None:
        print(f"ship: ступень {args.id} не найдена.")
        return 1
    if step.get("status") != "passed":
        print(f"ship: ступень {args.id} в статусе «{step.get('status')}», "
              f"а отгружать можно только passed. Отказ.")
        return 1
    ensure_clean()
    save_ladder_status(ladder_path, args.id, "shipped")
    git("add", "-A")
    git(*GIT_ID, "commit", "-m", f"ratchet: {args.id} shipped")
    print(f"ship: ступень {args.id} -> shipped (зафиксировано). "
          f"Следующую можно одобрить (approved=true).")
    return 0


# --------------------------------------------------------------------------- #
# status — read-only обзор лестницы
# --------------------------------------------------------------------------- #
def cmd_status(args) -> int:
    ladder_path = Path(args.ladder)
    ladder = load_ladder(ladder_path)
    cur = first_unshipped(ladder)
    cur_id = cur["id"] if cur else None
    print(f"лестница: {ladder_path.name}")
    for step in ladder:
        mark = "→" if step["id"] == cur_id else " "
        appr = "approved" if step.get("approved") else "pending-approval"
        print(f" {mark} {step['id']:4s} {step.get('status', '?'):8s} "
              f"[{appr:16s}] {step.get('title', '')}")
    return 0


# --------------------------------------------------------------------------- #
# verify — воспроизводимость вердикта: повторный прогон checks vs журнал
# --------------------------------------------------------------------------- #
def cmd_verify(args) -> int:
    ladder_path = Path(args.ladder)
    ladder = load_ladder(ladder_path)
    step = next((s for s in ladder if s["id"] == args.id), None)
    if step is None:
        print(f"verify: ступень {args.id} не найдена.")
        return 1

    outputs, ok = run_phase(step.get("checks", []), "check")
    verdict = "green" if ok else "red"
    rcs = [r["rc"] for r in outputs]

    entries = journal_entries(args.id)
    if not entries:
        print(f"verify: для {args.id} нет записей в журнале.")
        return 1
    last = entries[-1]
    j_checks = [c for c in last.get("checks", []) if c.get("phase") == "check"]
    j_rcs = [c["rc"] for c in j_checks]
    j_verdict = last.get("verdict")

    print(f"verify {args.id}: повторный прогон checks")
    print_outputs(outputs)
    print(f"\n  текущий вердикт : {verdict}  rc={rcs}")
    print(f"  журнал ({last['time']}): {j_verdict}  rc={j_rcs}")
    if verdict == j_verdict and rcs == j_rcs:
        print("  СОВПАДАЕТ — вердикт воспроизводим.")
        return 0
    print("  РАСХОЖДЕНИЕ — есть скрытое состояние, требуется разбор.")
    return 1


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ratchet", description="храповик сборки СВОД")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_ladder(sp):
        sp.add_argument("--ladder", default=str(LADDER_DEFAULT))

    t = sub.add_parser("tick", help="один удар")
    add_ladder(t)
    t.set_defaults(func=cmd_tick)

    s = sub.add_parser("ship", help="человек: passed -> shipped")
    s.add_argument("id")
    add_ladder(s)
    s.set_defaults(func=cmd_ship)

    st = sub.add_parser("status", help="состояние лестницы")
    add_ladder(st)
    st.set_defaults(func=cmd_status)

    v = sub.add_parser("verify", help="сверить вердикт с журналом")
    v.add_argument("id")
    add_ladder(v)
    v.set_defaults(func=cmd_verify)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
