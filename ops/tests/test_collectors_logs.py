from __future__ import annotations

import asyncio
from datetime import date, timedelta

from src.collectors import logs


def _write_logs(settings, today_lines, yesterday_lines):
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    (settings.log_dir / f"app-{today}.log").write_text(today_lines)
    (settings.log_dir / f"app-{yesterday}.log").write_text(yesterday_lines)


def test_counts_and_clusters(settings):
    _write_logs(
        settings,
        today_lines=(
            "2026-08-06 10:00:01 INFO ok\n"
            "2026-08-06 10:00:02 ERROR LLM request timed out after 600s\n"
            "2026-08-06 10:00:03 ERROR LLM request timed out after 600s\n"
            "2026-08-06 10:00:04 WARNING slow query\n"
        ),
        yesterday_lines="2026-08-05 10:00:02 ERROR one error\n",
    )

    sample = asyncio.run(logs.collect(settings))

    m = sample.metrics
    assert m["error_count"] == 2
    assert m["warn_count"] == 1
    assert m["error_count_yesterday"] == 1
    assert m["clusters"]["timeout"] == 2
    assert m["files_scanned"] == 1  # 当前窗口只数今天的文件
    assert len(sample.evidence) == 2
    assert "timed out" in sample.evidence[0]


def test_missing_log_dir_is_not_an_error(settings):
    settings.log_dir = settings.main_app_dir / "no-such-dir"

    sample = asyncio.run(logs.collect(settings))

    assert sample.ok is True
    assert sample.metrics["error_count"] == 0
    assert sample.metrics["files_scanned"] == 0


def test_snippets_newest_first_and_truncated(settings):
    lines = "".join(f"2026-08-06 10:{i:02d}:00 ERROR err-{i} {'x' * 600}\n" for i in range(30))
    _write_logs(settings, today_lines=lines, yesterday_lines="")

    sample = asyncio.run(logs.collect(settings))

    assert "err-29" in sample.evidence[0]           # 最新优先
    assert len(sample.evidence[0]) <= 520           # 截断（500 + 省略标记）
    assert len(sample.evidence) <= 20               # 上限条数
