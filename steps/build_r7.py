#!/usr/bin/env python3
"""Руки ступени R7: вносит инструменты сбора новостей в корень проекта.

Чертёж лежит в steps/r7_src/. Apply копирует модули в корень — так при
красной приёмке `git clean` снесёт копии из корня, а чертёж останется
инфраструктурой. Модули крупные (urllib, парсинг RSS, вызов Claude), поэтому
держим их отдельными файлами, а не строками-генераторами.
"""

import shutil
from pathlib import Path

SRC = Path(__file__).resolve().parent / "r7_src"
ROOT = Path(__file__).resolve().parent.parent
MODULES = ["news_fetch.py", "news_extract.py", "news_ingest.py"]

for name in MODULES:
    shutil.copyfile(SRC / name, ROOT / name)
    print(f"build_r7: внесён {name}")
