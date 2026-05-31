#!/usr/bin/env python3
"""article_fetch — скачать тело статей по ссылкам из raw.jsonl (только stdlib).

Слой СБОРА, не приёмки. Сеть трогается только здесь. Граница доверия —
ПРОИСХОЖДЕНИЕ ссылок: ходим лишь по link'ам из raw.jsonl, а тот собран из лент
белого списка sources_svo.json. Хост самой статьи (например, www.bbc.com)
обычно отличается от хоста ленты (feeds.bbci.co.uk), поэтому белый список по
хосту тут не применим — доверяем источнику ссылки, а не домену.

Чистая функция `extract_text` (html.parser) вытаскивает видимый текст блочных
тегов, выбрасывая script/style. Её и проверяет приёмка на замороженной
HTML-фикстуре — без сети, детерминированно.

    python article_fetch.py              # все некэшированные ссылки из raw.jsonl
    python article_fetch.py bbc tass     # только эти источники
Результат дописывается в articles.jsonl: по строке JSON на статью.
Кэш по link (article_cache.json) не даёт ходить по одной ссылке дважды.
"""

from __future__ import annotations

import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import env

env.load_dotenv()

ROOT = Path(__file__).resolve().parent
RAW = env.data_path("raw.jsonl")
ARTICLES = env.data_path("articles.jsonl")
CACHE = env.data_path("article_cache.json")
TIMEOUT = 25
USER_AGENT = "svod-article-fetch/1.0 (+research)"

BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}
SKIP_TAGS = {"script", "style", "noscript", "head", "header", "footer", "nav", "aside"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _TextExtractor(HTMLParser):
    """Собирает текст блочных тегов, игнорируя служебные секции."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._block_depth = 0
        self._buf: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag in BLOCK_TAGS:
            self._flush()
            self._block_depth += 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in BLOCK_TAGS and self._block_depth:
            self._block_depth -= 1
            self._flush()

    def handle_data(self, data):
        if self._skip_depth or not self._block_depth:
            return
        self._buf.append(data)

    def _flush(self):
        text = "".join(self._buf).strip()
        if text:
            self.parts.append(text)
        self._buf = []


def extract_text(html: str) -> str:
    """HTML -> чистый текст абзацев (чистая функция, основа приёмки)."""
    parser = _TextExtractor()
    parser.feed(html)
    parser._flush()
    paras = [re.sub(r"\s+", " ", p).strip() for p in parser.parts]
    paras = [p for p in paras if len(p) > 1]
    return "\n\n".join(paras)


def load_raw() -> list[dict]:
    if not RAW.exists():
        return []
    rows = []
    for line in RAW.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def load_cache() -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    env.ensure_data_dir()
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                     encoding="utf-8")


def fetch_html(url: str, retries: int = 3) -> str:
    """Скачать HTML с повторами; терпимо к обрыву chunked-ответа (IncompleteRead)."""
    scheme = urlsplit(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"недопустимая схема ссылки: {scheme!r}")
    last_exc: Exception | None = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                chunks: list[bytes] = []
                while True:
                    try:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    except http.client.IncompleteRead as exc:
                        if exc.partial:
                            chunks.append(exc.partial)
                        break
                raw = b"".join(chunks)
            if raw:
                return raw.decode("utf-8", errors="replace")
        except (urllib.error.URLError, ValueError, OSError,
                http.client.IncompleteRead) as exc:
            last_exc = exc
    raise last_exc or RuntimeError(f"пустой ответ: {url}")


def append_articles(rows: list[dict]) -> None:
    env.ensure_data_dir()
    with ARTICLES.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rows = load_raw()
    if argv:
        want = set(argv)
        rows = [r for r in rows if r["source"] in want]
    cache = load_cache()
    fetched = 0
    failed = 0
    batch: list[dict] = []
    for r in rows:
        link = r.get("link", "")
        if not link or link in cache:
            continue
        try:
            text = extract_text(fetch_html(link))
            cache[link] = now_iso()
            if not text:
                failed += 1
                continue
            batch.append({
                "source": r["source"],
                "source_name": r.get("source_name", r["source"]),
                "title": r.get("title", ""),
                "link": link,
                "published": r.get("published", ""),
                "text": text,
                "fetched_at": now_iso(),
            })
            fetched += 1
            if len(batch) >= 20:
                append_articles(batch)
                batch = []
        except Exception as exc:
            failed += 1
            cache[link] = f"error: {exc}"
            print(f"  {r.get('source', '?'):14s} ОШИБКА: {link[:70]} — {exc}")
    if batch:
        append_articles(batch)
    save_cache(cache)
    print(f"article_fetch: статей +{fetched}, осечек {failed} -> {ARTICLES.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
