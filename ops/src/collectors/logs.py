from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from src.collectors.base import Sample

_ERROR_RE = re.compile(r"\bERROR\b")
_WARN_RE = re.compile(r"\bWARNING\b")

_PATTERNS = [
    (re.compile(r"timed?\s*out|timeout", re.I), "timeout"),
    (re.compile(r"connection\s*(refused|reset|error)|connect.*failed", re.I), "connection"),
    (re.compile(r"\b5\d{2}\b.*(bank|接口|api)|status[_ ]?code[=: ]?5\d{2}", re.I), "http_5xx"),
    (re.compile(r"out of memory|MemoryError", re.I), "memory"),
    (re.compile(r"unauthorized|forbidden|\b40[13]\b|api[_ ]?key", re.I), "auth"),
]

_TAIL_BYTES = 5 * 1024 * 1024
_MAX_SNIPPETS = 20
_SNIPPET_CHARS = 500


def _read_tail(path) -> str:
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > _TAIL_BYTES:
            f.seek(-_TAIL_BYTES, 2)
        return f.read().decode("utf-8", errors="replace")


def _scan_file(path) -> dict:
    errors = warns = 0
    clusters: dict[str, int] = {}
    snippets: list[str] = []
    for line in _read_tail(path).splitlines():
        if _ERROR_RE.search(line):
            errors += 1
            for pattern, label in _PATTERNS:
                if pattern.search(line):
                    clusters[label] = clusters.get(label, 0) + 1
                    break
            snippet = line.strip()
            if len(snippet) > _SNIPPET_CHARS:
                snippet = snippet[:_SNIPPET_CHARS] + " …(截断)"
            snippets.append(snippet)
        elif _WARN_RE.search(line):
            warns += 1
    snippets.reverse()  # 最新优先
    return {
        "errors": errors,
        "warns": warns,
        "clusters": clusters,
        "snippets": snippets[:_MAX_SNIPPETS],
    }


def _count_errors(path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in _read_tail(path).splitlines() if _ERROR_RE.search(line))


def _scan_sync(settings) -> Sample:
    log_dir = settings.log_dir
    if not log_dir.is_dir():
        return Sample("logs", True, metrics={
            "error_count": 0, "warn_count": 0, "error_count_yesterday": 0,
            "clusters": {}, "files_scanned": 0,
        })

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    current_files = []
    for name in (f"app-{today}.log", "app.log"):
        p = log_dir / name
        if p.exists():
            current_files.append(p)

    errors = warns = 0
    clusters: dict[str, int] = {}
    snippets: list[str] = []
    for path in current_files:
        result = _scan_file(path)
        errors += result["errors"]
        warns += result["warns"]
        for label, count in result["clusters"].items():
            clusters[label] = clusters.get(label, 0) + count
        snippets.extend(result["snippets"])

    yesterday_errors = _count_errors(log_dir / f"app-{yesterday}.log")

    return Sample(
        "logs",
        True,
        metrics={
            "error_count": errors,
            "warn_count": warns,
            "error_count_yesterday": yesterday_errors,
            "clusters": clusters,
            "files_scanned": len(current_files),
        },
        evidence=snippets[:_MAX_SNIPPETS],
    )


async def collect(settings) -> Sample:
    return await asyncio.to_thread(_scan_sync, settings)
