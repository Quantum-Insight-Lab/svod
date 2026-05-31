#!/usr/bin/env python3
"""Руки R12: оркестратор vector + arbiter."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(__file__).resolve().parent / "r12_src"
for name in ("vector.py", "arbiter.py"):
    src = SRC / name
    if src.is_file():
        shutil.copyfile(src, ROOT / name)
        print(f"build_r12: {name}")
