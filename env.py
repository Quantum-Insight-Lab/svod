#!/usr/bin/env python3
"""Загрузка переменных из .env в os.environ (только stdlib).

Не перезаписывает переменные, уже заданные в окружении процесса —
удобно для CI и ручного override в PowerShell.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def load_dotenv(path: Path | None = None) -> None:
    env_file = path or ENV_FILE
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val
