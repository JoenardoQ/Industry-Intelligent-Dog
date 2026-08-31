"""Reproducible 10k-document local pagination benchmark (temporary data only)."""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from pathlib import Path

from intdog_core import IntDogService


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="intdog-page-benchmark-") as temp:
        service = IntDogService(Path(temp))
        service.create_industry("AI", "人工智能")
        rows = [{
            "title": f"Benchmark item {index:05d}",
            "url": f"https://benchmark.invalid/{index}",
            "source": f"Publisher {index % 31:02d}",
            "abstract": "bounded pagination fixture",
        } for index in range(10_000)]
        started = time.perf_counter()
        service.import_daily("AI", "news", "2026-08-31", rows)
        insert_seconds = time.perf_counter() - started
        durations = []
        page = None
        for _ in range(30):
            started = time.perf_counter()
            page = service.repo.page_documents(
                "AI", sort="title", limit=50, query="Benchmark")
            durations.append((time.perf_counter() - started) * 1000)
        ordered = sorted(durations)
        p95 = ordered[max(0, int(len(ordered) * .95) - 1)]
        print(json.dumps({
            "fixture_documents": 10_000,
            "page_size": len(page["items"] if page else []),
            "total": page["total"] if page else 0,
            "insert_seconds": round(insert_seconds, 3),
            "median_query_ms": round(statistics.median(durations), 3),
            "p95_query_ms": round(p95, 3),
            "cursor_present": bool(page and page["next_cursor"]),
        }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
