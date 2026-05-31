#!/usr/bin/env python3
"""Корень проекта, .env и каталог data/ для рабочих артефактов.

Переменные окружения (см. .env.example):
  SVOD_DATA — каталог данных (по умолчанию <корень>/data)
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
_dotenv_loaded = False


def load_dotenv(path: Path | None = None) -> None:
    global _dotenv_loaded
    env_file = path or ENV_FILE
    if not env_file.is_file():
        _dotenv_loaded = True
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
    _dotenv_loaded = True


def _boot() -> None:
    if not _dotenv_loaded:
        load_dotenv()


def data_dir() -> Path:
    """Каталог рабочих артефактов: svod.json, raw.jsonl, кэши…"""
    _boot()
    custom = os.environ.get("SVOD_DATA", "").strip()
    if custom:
        return Path(custom)
    return ROOT / "data"


def data_path(name: str) -> Path:
    return data_dir() / name


def ensure_data_dir() -> Path:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def fixtures_dir() -> Path:
    return ROOT / "fixtures"
