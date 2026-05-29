#!/usr/bin/env python3
"""news_fetch — сбор заголовков из RSS-лент белого списка (только stdlib).

Слой СБОРА, не приёмки. Сеть трогается только здесь и только для хостов из
sources_svo.json. Разбор XML (`parse_rss`) отделён от сети, поэтому приёмка
гоняет его на замороженной фикстуре — детерминированно и без интернета.

Запуск (вручную, под контролем человека):
    python news_fetch.py                # все источники белого списка
    python news_fetch.py bbc tass       # только указанные id
Результат дописывается в raw.jsonl: по строке JSON на заголовок.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources_svo.json"
RAW = ROOT / "raw.jsonl"
TIMEOUT = 20
USER_AGENT = "svod-news-fetch/1.0 (+research)"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_sources() -> list[dict]:
    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    return data["sources"]


def whitelist(sources: list[dict]) -> set[str]:
    return {urlsplit(s["rss"]).netloc.lower() for s in sources}


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_rss(xml_text: str) -> list[dict]:
    """Разобрать ленту RSS 2.0 / RDF / Atom в список {title, link, published}.

    Чистая функция без сети — основа детерминированной приёмки.
    """
    root = ET.fromstring(xml_text.strip())
    items: list[dict] = []
    for node in root.iter():
        tag = _strip_ns(node.tag)
        if tag not in ("item", "entry"):
            continue
        title = ""
        link = ""
        published = ""
        for child in node:
            ctag = _strip_ns(child.tag)
            if ctag == "title" and not title:
                title = _text(child)
            elif ctag == "link":
                # RSS: текст узла; Atom: атрибут href
                link = _text(child) or child.attrib.get("href", "") or link
            elif ctag in ("pubdate", "published", "updated", "date") and not published:
                published = _text(child)
        if title:
            items.append({"title": title, "link": link, "published": published})
    return items


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def fetch_source(src: dict, allowed: set[str]) -> list[dict]:
    host = urlsplit(src["rss"]).netloc.lower()
    if host not in allowed:
        raise PermissionError(f"хост вне белого списка: {host}")
    xml_text = fetch_url(src["rss"])
    fetched = now_iso()
    rows = []
    for item in parse_rss(xml_text):
        rows.append({
            "source": src["id"],
            "source_name": src.get("name", src["id"]),
            "title": item["title"],
            "link": item["link"],
            "published": item["published"],
            "fetched_at": fetched,
        })
    return rows


def append_raw(rows: list[dict]) -> None:
    with RAW.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sources = load_sources()
    allowed = whitelist(sources)
    if argv:
        want = set(argv)
        sources = [s for s in sources if s["id"] in want]
        if not sources:
            print(f"news_fetch: нет таких источников: {sorted(want)}")
            return 1
    total = 0
    for src in sources:
        try:
            rows = fetch_source(src, allowed)
            append_raw(rows)
            total += len(rows)
            print(f"  {src['id']:16s} +{len(rows)} заголовков")
        except Exception as exc:  # сеть/парсинг — не валим весь прогон
            print(f"  {src['id']:16s} ОШИБКА: {exc}")
    print(f"news_fetch: всего +{total} заголовков -> {RAW.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
