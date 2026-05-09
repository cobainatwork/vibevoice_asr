"""
Dataset exporter — 內部 0-indexed speaker → 對外格式（json 不轉、srt/xlsx 1-indexed）。

See SPEC.md §9.4.
"""
from __future__ import annotations

import io
import json
from typing import Literal

from openpyxl import Workbook

from app.utils.time_utils import seconds_to_hms, seconds_to_srt

ExportFormat = Literal["json", "srt", "xlsx"]


def export_item(item, format: ExportFormat) -> tuple[bytes, str, str]:
    """
    回傳 (content_bytes, content_type, filename).

    item: DatasetItem ORM row（duck-typed: 只用 .id 與 .label）。
    """
    if format == "json":
        return _export_json(item)
    if format == "srt":
        return _export_srt(item)
    if format == "xlsx":
        return _export_xlsx(item)
    raise ValueError(f"Unsupported export format: {format}")


def _export_json(item) -> tuple[bytes, str, str]:
    content = json.dumps(item.label, ensure_ascii=False, indent=2).encode("utf-8")
    return content, "application/json", f"dataset-{item.id}.json"


def _export_srt(item) -> tuple[bytes, str, str]:
    lines: list[str] = []
    for i, seg in enumerate(item.label["segments"], start=1):
        lines.append(str(i))
        lines.append(f"{seconds_to_srt(seg['start'])} --> {seconds_to_srt(seg['end'])}")
        lines.append(f"Speaker {seg['speaker'] + 1}: {seg['text']}")
        lines.append("")  # blank line
    content = "\n".join(lines).encode("utf-8")
    return content, "application/x-subrip", f"dataset-{item.id}.srt"


def _export_xlsx(item) -> tuple[bytes, str, str]:
    wb = Workbook()
    ws = wb.active
    ws.title = "dataset"
    ws.append(["start_time", "end_time", "speaker", "text"])
    for seg in item.label["segments"]:
        ws.append(
            [
                seconds_to_hms(seg["start"], with_ms=True),
                seconds_to_hms(seg["end"], with_ms=True),
                seg["speaker"] + 1,
                seg["text"],
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return (
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"dataset-{item.id}.xlsx",
    )
