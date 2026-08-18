from __future__ import annotations

from src.infrastructure.files.file_reader import read_file_records, read_file_summary


def summarize_uploaded_file(file_path: str) -> str:
    return read_file_summary(file_path)


def read_uploaded_activity_records(file_path: str, max_rows: int = 500) -> dict:
    return read_file_records(file_path, max_rows=max_rows)
