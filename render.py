#!/usr/bin/env python3
"""render — HTML-интерфейс чтения поверх живой базы СВОД.

Строит report.html из текущего состояния: темы, утверждения, вычисленная
уверенность и провенанс (кто поддержал, с какой надёжностью). HTML — функция
живой базы: меняются надёжности/наблюдения -> меняется и страница, без правок
кода рендера.
"""

from __future__ import annotations

import html
import sys

import env
import svod

env.load_dotenv()

OUT = env.data_path("report.html")


def render(state: dict) -> str:
    conf = svod.compute_confidences(state)
    parts = ["<!doctype html><meta charset=utf-8><title>СВОД</title>",
             "<h1>СВОД — живой свод утверждений</h1>"]
    for topic in sorted(state["topics"]):
        parts.append(f"<h2>{html.escape(topic)}</h2><ul>")
        rows = []
        for stmt in state["topics"][topic]["claims"]:
            c = conf.get(svod.claim_key(topic, stmt), 0.0)
            rows.append((c, stmt))
        for c, stmt in sorted(rows, reverse=True):
            srcs = svod.supporters(state, topic, stmt)
            prov = ", ".join(
                f"{html.escape(s)}({state['sources'][s]['reliability']:.2f})"
                for s in srcs
            )
            parts.append(
                f"<li><b>{c:.3f}</b> {html.escape(stmt)} "
                f"<small>[{prov}]</small></li>"
            )
        parts.append("</ul>")
    return "\n".join(parts)


def main() -> int:
    env.ensure_data_dir()
    state = svod.load_state()
    OUT.write_text(render(state), encoding="utf-8")
    print(f"render: {OUT.name} обновлён ({len(state['topics'])} тем)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
