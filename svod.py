#!/usr/bin/env python3
"""SVOD — ядро свода утверждений.

Хранит утверждения с провенансом (кто, когда), вычисляет уверенность из
надёжности источников и обучает надёжности источников по принципу truth
discovery (EM-итерации). Только стандартная библиотека.

Состояние: svod.json в каталоге проекта. Команды:
  seed                       — заложить демонстрационный набор данных
  add SRC TOPIC STATEMENT    — записать наблюдение (источник утверждает claim)
  ingest FILE                — собрать наблюдения из файла (SRC | TOPIC | STMT)
  ask TOPIC                  — показать утверждения темы с уверенностью и провенансом
  learn [N]                  — N итераций обучения надёжностей (по умолчанию 3)
  sources                    — список источников с надёжностью
  top [N]                    — топ утверждений по уверенности
  history [N]                — последние N записей журнала уверенности
  tick                       — удар: пересчитать, снять снимок, отчитаться
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# вывод всегда в UTF-8, независимо от кодовой страницы консоли
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Путь к состоянию. По умолчанию — svod.json рядом с модулем, но его можно
# переопределить переменной окружения SVOD_STATE. Храповик пользуется этим,
# чтобы прогонять приёмку на ОТДЕЛЬНОМ временном файле и не трогать рабочую базу.
STATE_PATH = Path(os.environ.get("SVOD_STATE") or
                  (Path(__file__).resolve().parent / "svod.json"))

R_MIN, R_MAX = 0.05, 0.95   # надёжность не схлопывается в 0/1
R_INIT = 0.5                # априорная надёжность нового источника


# --------------------------------------------------------------------------- #
# Состояние
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_state() -> dict:
    return {
        "version": 1,
        "sources": {},        # name -> {reliability, added}
        "topics": {},         # topic -> {claims: {statement -> {added}}}
        "observations": [],   # [{source, topic, statement, time}]
        "history": [],        # [{time, op, note, snapshot}]
    }


def load_state() -> dict:
    if not STATE_PATH.exists():
        return empty_state()
    with STATE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state: dict) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    tmp.replace(STATE_PATH)


# --------------------------------------------------------------------------- #
# Модель уверенности и обучение
# --------------------------------------------------------------------------- #
def claim_key(topic: str, statement: str) -> str:
    return f"{topic} = {statement}"


def supporters(state: dict, topic: str, statement: str) -> list[str]:
    """Различные источники, утверждающие данный claim (без повторов)."""
    seen = []
    for ob in state["observations"]:
        if ob["topic"] == topic and ob["statement"] == statement:
            if ob["source"] not in seen:
                seen.append(ob["source"])
    return seen


def source_claims(state: dict) -> dict:
    """Источник -> список различных ключей утверждений, которые он поддержал."""
    out: dict = {n: [] for n in state["sources"]}
    for ob in state["observations"]:
        key = claim_key(ob["topic"], ob["statement"])
        if key not in out[ob["source"]]:
            out[ob["source"]].append(key)
    return out


def compute_confidences(state: dict) -> dict:
    """Уверенность каждого claim.

    Внутри темы взаимоисключающие утверждения делят «вес» поддержавших их
    источников (сумма надёжностей). Опорная альтернатива NULL с весом R_INIT
    задаёт априорный скепсис: одинокое слабое утверждение не дотянет до 1.0,
    спорная тема (несколько равновесных версий) расщепляет уверенность вниз.
    """
    rel = {n: s["reliability"] for n, s in state["sources"].items()}
    conf: dict = {}
    for topic, tdata in state["topics"].items():
        belief = {}
        for statement in tdata["claims"]:
            srcs = supporters(state, topic, statement)
            belief[statement] = sum(rel.get(s, R_INIT) for s in srcs)
        denom = R_INIT + sum(belief.values())  # NULL-альтернатива
        for statement, b in belief.items():
            conf[claim_key(topic, statement)] = b / denom if denom else 0.0
    return conf


def learn(state: dict, iterations: int) -> dict:
    """Truth discovery (Sums/Investment): доверие к источнику и вера в
    утверждение усиливают друг друга. Вера(claim) = сумма доверий
    поддержавших источников (нормируется к [0,1]); доверие(источник) =
    средняя вера поддержанных им утверждений. Итерируем N раз."""
    before = {n: s["reliability"] for n, s in state["sources"].items()}
    trust = {n: s["reliability"] for n, s in state["sources"].items()}
    claims_of = source_claims(state)
    for _ in range(iterations):
        belief: dict = {}
        for topic, tdata in state["topics"].items():
            for statement in tdata["claims"]:
                srcs = supporters(state, topic, statement)
                belief[claim_key(topic, statement)] = sum(trust[s] for s in srcs)
        max_b = max(belief.values(), default=0.0) or 1.0
        belief = {k: v / max_b for k, v in belief.items()}
        for src, keys in claims_of.items():
            if not keys:
                continue
            trust[src] = sum(belief[k] for k in keys) / len(keys)
    for name in state["sources"]:
        state["sources"][name]["reliability"] = min(max(trust[name], R_MIN), R_MAX)
    after = {n: s["reliability"] for n, s in state["sources"].items()}
    return {"before": before, "after": after}


def snapshot(state: dict, op: str, note: str = "") -> dict:
    conf = compute_confidences(state)
    entry = {
        "time": now_iso(),
        "op": op,
        "note": note,
        "snapshot": {k: round(v, 4) for k, v in conf.items()},
    }
    state["history"].append(entry)
    return entry


# --------------------------------------------------------------------------- #
# Команды
# --------------------------------------------------------------------------- #
def ensure_source(state: dict, name: str) -> None:
    if name not in state["sources"]:
        state["sources"][name] = {"reliability": R_INIT, "added": now_iso()}


def ensure_claim(state: dict, topic: str, statement: str) -> None:
    t = state["topics"].setdefault(topic, {"claims": {}})
    if statement not in t["claims"]:
        t["claims"][statement] = {"added": now_iso()}


def record_observation(state: dict, source: str, topic: str, statement: str) -> None:
    ensure_source(state, source)
    ensure_claim(state, topic, statement)
    state["observations"].append(
        {"source": source, "topic": topic, "statement": statement, "time": now_iso()}
    )


SEED = [
    # source, topic, statement
    ("alice", "форма_земли", "шар"),
    ("bob",   "форма_земли", "шар"),
    ("dave",  "форма_земли", "шар"),
    ("carol", "форма_земли", "плоская"),

    ("alice", "вода_кипит_при", "100C"),
    ("bob",   "вода_кипит_при", "100C"),
    ("dave",  "вода_кипит_при", "100C"),

    ("alice", "вакцины", "безопасны"),
    ("bob",   "вакцины", "безопасны"),
    ("carol", "вакцины", "опасны"),

    # спорная тема: два отдельных источника тянут в разные стороны
    ("erin",  "лучший_обед", "пицца"),
    ("frank", "лучший_обед", "суши"),
    ("carol", "лучший_обед", "тако"),
]


def cmd_seed(args) -> int:
    state = empty_state()
    for src, topic, stmt in SEED:
        record_observation(state, src, topic, stmt)
    snapshot(state, "seed", "демонстрационный набор заложен")
    save_state(state)
    print(f"seed: источников={len(state['sources'])} "
          f"тем={len(state['topics'])} "
          f"наблюдений={len(state['observations'])}")
    _print_top(state, 5)
    return 0


def cmd_add(args) -> int:
    state = load_state()
    record_observation(state, args.source, args.topic, args.statement)
    snapshot(state, "add", f"{args.source}: {claim_key(args.topic, args.statement)}")
    save_state(state)
    conf = compute_confidences(state)
    key = claim_key(args.topic, args.statement)
    print(f"add: {args.source} -> «{key}»  уверенность={conf.get(key, 0):.3f}")
    return 0


def cmd_ingest(args) -> int:
    path = Path(args.file)
    if not path.is_absolute():
        path = STATE_PATH.parent / path
    if not path.exists():
        print(f"ingest: файл не найден: {path}")
        return 1
    state = load_state()
    added = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            print(f"ingest: пропущена строка (нужно SRC | TOPIC | STMT): {line!r}")
            continue
        record_observation(state, *parts)
        added += 1
    snapshot(state, "ingest", f"{path.name}: +{added} наблюдений")
    save_state(state)
    print(f"ingest: собрано наблюдений={added} из {path.name}")
    return 0


def cmd_ask(args) -> int:
    state = load_state()
    topic = args.topic
    if topic not in state["topics"]:
        print(f"ask: тема не найдена: {topic}")
        return 1
    conf = compute_confidences(state)
    print(f"тема: {topic}")
    rows = []
    for statement in state["topics"][topic]["claims"]:
        key = claim_key(topic, statement)
        rows.append((conf.get(key, 0.0), statement))
    for c, statement in sorted(rows, reverse=True):
        srcs = supporters(state, topic, statement)
        prov = ", ".join(
            f"{s}({state['sources'][s]['reliability']:.2f})" for s in srcs
        )
        print(f"  [{c:5.3f}] {statement}")
        print(f"          провенанс: {prov}")
    return 0


def cmd_learn(args) -> int:
    state = load_state()
    n = args.iterations
    delta = learn(state, n)
    snapshot(state, "learn", f"{n} итераций")
    save_state(state)
    print(f"learn: {n} итераций, обновлены надёжности источников:")
    for name in sorted(delta["before"]):
        b, a = delta["before"][name], delta["after"][name]
        print(f"  {name:8s} {b:.3f} -> {a:.3f}  ({a - b:+.3f})")
    return 0


def cmd_sources(args) -> int:
    state = load_state()
    if not state["sources"]:
        print("sources: пусто")
        return 0
    print("источник   надёжность  добавлен")
    items = sorted(state["sources"].items(),
                   key=lambda kv: kv[1]["reliability"], reverse=True)
    for name, s in items:
        print(f"  {name:8s} {s['reliability']:.3f}     {s.get('added', '?')}")
    return 0


def _print_top(state: dict, n: int) -> None:
    conf = compute_confidences(state)
    if not conf:
        print("  (утверждений нет)")
        return
    for key, c in sorted(conf.items(), key=lambda kv: kv[1], reverse=True)[:n]:
        print(f"  [{c:5.3f}] {key}")


def cmd_top(args) -> int:
    state = load_state()
    print(f"top {args.n}:")
    _print_top(state, args.n)
    return 0


def cmd_history(args) -> int:
    state = load_state()
    hist = state["history"][-args.n:]
    if not hist:
        print("history: пусто")
        return 0
    for e in hist:
        print(f"{e['time']}  {e['op']:8s} {e.get('note', '')}")
        for key, c in sorted(e["snapshot"].items(), key=lambda kv: kv[1], reverse=True):
            print(f"      [{c:5.3f}] {key}")
    return 0


def cmd_tick(args) -> int:
    """Удар сердцебиения: пересчитать уверенности, снять снимок, отчитаться."""
    state = load_state()
    entry = snapshot(state, "tick", "пересчёт по сердцебиению")
    save_state(state)
    n_claims = sum(len(t["claims"]) for t in state["topics"].values())
    print(f"tick @ {entry['time']}: источников={len(state['sources'])} "
          f"тем={len(state['topics'])} утверждений={n_claims}")
    _print_top(state, 3)
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="svod", description="ядро свода утверждений")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("seed", help="заложить демонстрационный набор").set_defaults(func=cmd_seed)

    a = sub.add_parser("add", help="записать наблюдение")
    a.add_argument("source")
    a.add_argument("topic")
    a.add_argument("statement")
    a.set_defaults(func=cmd_add)

    i = sub.add_parser("ingest", help="собрать наблюдения из файла")
    i.add_argument("file")
    i.set_defaults(func=cmd_ingest)

    k = sub.add_parser("ask", help="показать тему")
    k.add_argument("topic")
    k.set_defaults(func=cmd_ask)

    l = sub.add_parser("learn", help="обучить надёжности")
    l.add_argument("iterations", nargs="?", type=int, default=3)
    l.set_defaults(func=cmd_learn)

    sub.add_parser("sources", help="список источников").set_defaults(func=cmd_sources)

    t = sub.add_parser("top", help="топ утверждений")
    t.add_argument("n", nargs="?", type=int, default=10)
    t.set_defaults(func=cmd_top)

    h = sub.add_parser("history", help="журнал уверенности")
    h.add_argument("n", nargs="?", type=int, default=5)
    h.set_defaults(func=cmd_history)

    sub.add_parser("tick", help="удар сердцебиения").set_defaults(func=cmd_tick)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
