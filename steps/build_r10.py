#!/usr/bin/env python3
"""Руки R10: article_walk — оффлайн проход по статьям."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = Path(__file__).resolve().parent / "r10_src" / "article_walk.py"
if src.is_file():
    shutil.copyfile(src, ROOT / "article_walk.py")
    print("build_r10: article_walk.py")
else:
    print("build_r10: article_walk.py уже на месте")
