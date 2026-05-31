#!/usr/bin/env python3
"""Сердцебиение храповика: один удар = один `ratchet tick`, сводка в лог.

Ставится на расписание (cron / Планировщик задач Windows / heartbeat OpenClaw).
За запуск делает РОВНО ОДИН tick — никакого перебора ступеней, как и требует
храповик. Сводку, которую печатает tick, дописывает в beats.log (провенанс
ударов) и выводит в stdout, чтобы планировщик/OpenClaw доставил её человеку.

Код решения не принимает: продвижение по лестнице по-прежнему только через
человеческий шлюз (approved / ship). Это просто таймер поверх tick.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import env

env.load_dotenv()

ROOT = env.ROOT
BEATS = env.data_path("beats.log")


def main() -> int:
    env.ensure_data_dir()
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "ratchet.py"), "tick"],
        cwd=str(ROOT), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    summary = (proc.stdout or "") + (proc.stderr or "")
    with BEATS.open("a", encoding="utf-8") as fh:
        fh.write(f"\n===== beat {ts} (rc={proc.returncode}) =====\n")
        fh.write(summary)
        if not summary.endswith("\n"):
            fh.write("\n")
    sys.stdout.write(summary)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
