#!/usr/bin/env python3
"""collect — обёртка ручного пайплайна сбора (вне tick, под контролем человека).

Не заменяет храповик: сеть и LLM здесь, приёмка — отдельно на лестнице.
После extract нужен человеческий шлюз approved=true и news_ingest.

    python collect.py              # fetch RSS → статьи → extract
    python collect.py --dry        # показать шаги без запуска
    python collect.py fetch        # только news_fetch + article_fetch
    python collect.py extract      # только article_extract
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import env

env.load_dotenv()

ROOT = env.ROOT

PIPELINE: list[tuple[str, str]] = [
    ("news_fetch.py", "RSS → data/raw.jsonl"),
    ("article_fetch.py", "Ссылки → data/articles.jsonl"),
    ("article_extract.py", "Тела → data/candidates.jsonl (Sonnet)"),
]

PARTS = {
    "fetch": PIPELINE[:2],
    "extract": PIPELINE[2:],
}


def run_step(script: str, dry: bool) -> int:
    if dry:
        print(f"  [dry] python {script}")
        return 0
    print(f"--- {script} ---")
    proc = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=str(ROOT),
    )
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    dry = "--dry" in argv
    argv = [a for a in argv if a != "--dry"]
    if argv and argv[0] in PARTS:
        steps = PARTS[argv[0]]
    else:
        steps = PIPELINE
    env.ensure_data_dir()
    print("collect: пайплайн сбора (данные в data/)")
    for script, label in steps:
        print(f"  → {label}")
        rc = run_step(script, dry)
        if rc != 0:
            print(f"collect: останов на {script} (rc={rc})")
            return rc
    if not dry:
        print("collect: готово. Дальше: approved=true в candidates, news_ingest.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
