#!/usr/bin/env python3
"""Арбитр — независимый суд инвариантов (не та логика, что писала ход).

Детерминированные проверки из invariants.py. LLM здесь не используется.
"""

from __future__ import annotations

import json
import sys

import invariants

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass


def dashboard(step_ids: list[str] | None = None) -> dict:
    results = invariants.run_all(step_ids)
    return {
        "slice_ok": all(r["ok"] for r in results),
        "invariants": results,
    }


def print_dashboard(d: dict) -> None:
    print("=== АРБИТР · дашборд среза ===")
    for r in d["invariants"]:
        mark = "OK" if r["ok"] else "FAIL"
        print(f"  [{mark}] {r['id']}: {r['detail']}")
    verdict = "ЗЕЛЁНЫЙ" if d["slice_ok"] else "КРАСНЫЙ"
    print(f"\nСрез: {verdict}")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    as_json = "--json" in argv
    d = dashboard()
    if as_json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    else:
        print_dashboard(d)
    return 0 if d["slice_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
