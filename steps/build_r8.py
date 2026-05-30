#!/usr/bin/env python3
"""Руки ступени R8: вносит инструменты извлечения из тела статьи в корень.

Чертёж лежит в steps/r8_src/. Apply копирует модули в корень — при красной
приёмке `git clean` снесёт копии из корня, а чертёж останется инфраструктурой.
"""

import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parent / "r8_src"
ROOT = Path(__file__).resolve().parent.parent
MODULES = ["article_fetch.py", "article_extract.py"]

for name in MODULES:
    shutil.copyfile(SRC / name, ROOT / name)
    print(f"build_r8: внесён {name}")
