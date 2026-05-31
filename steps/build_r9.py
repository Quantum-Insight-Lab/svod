#!/usr/bin/env python3
"""Руки ступени R9: структура проекта — data/, fixtures/, collect."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
(DATA / ".gitkeep").touch(exist_ok=True)

MIGRATE = (
    "svod.json", "raw.jsonl", "candidates.jsonl", "extract_cache.json",
    "articles.jsonl", "article_cache.json", "article_extract_cache.json",
    "journal.jsonl", "beats.log", "report.html", ".accept_state.json",
)
for name in MIGRATE:
    src, dst = ROOT / name, DATA / name
    if src.is_file() and not dst.exists():
        shutil.move(str(src), str(dst))
        print(f"build_r9: перенесён {name} -> data/")

FIX = ROOT / "fixtures"
FIX.mkdir(exist_ok=True)
for name in ("sample_feed.txt", "echo_feed.txt"):
    src, dst = ROOT / name, FIX / name
    if src.is_file() and not dst.exists():
        shutil.move(str(src), str(dst))
        print(f"build_r9: перенесён {name} -> fixtures/")
    elif src.is_file() and dst.exists():
        src.unlink()

shutil.copyfile(
    Path(__file__).resolve().parent / "r9_src" / "collect.py",
    ROOT / "collect.py",
)
print("build_r9: внесён collect.py")

for mod, sub in (
    ("news_fetch.py", "r7_src"), ("news_extract.py", "r7_src"),
    ("news_ingest.py", "r7_src"),
    ("article_fetch.py", "r8_src"), ("article_extract.py", "r8_src"),
):
    src = Path(__file__).resolve().parent / sub / mod
    if src.is_file():
        shutil.copyfile(src, ROOT / mod)
        print(f"build_r9: обновлён {mod}")
