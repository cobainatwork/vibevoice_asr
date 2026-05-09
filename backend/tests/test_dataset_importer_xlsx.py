import pytest
from pathlib import Path
from openpyxl import Workbook

from app.errors import AppError, ErrorCode
from app.services.dataset_importer import parse_xlsx


def _make_xlsx(tmp_path: Path, rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    p = tmp_path / "label.xlsx"
    wb.save(p)
    return p


def test_parse_xlsx_basic_float_seconds(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["start_time", "end_time", "speaker", "text"],
        [0.0, 3.45, 0, "hello"],
        [3.45, 7.20, 1, "world"],
    ])
    segs = parse_xlsx(p)
    assert len(segs) == 2
    assert segs[0] == {"start": 0.0, "end": 3.45, "speaker": 0, "text": "hello"}
    assert segs[1] == {"start": 3.45, "end": 7.20, "speaker": 1, "text": "world"}


def test_parse_xlsx_hms_time_format(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["start_time", "end_time", "speaker", "text"],
        ["0:00:00.00", "0:00:03.45", 0, "hello"],
    ])
    segs = parse_xlsx(p)
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] == pytest.approx(3.45)


def test_parse_xlsx_mmss_time_format(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["start_time", "end_time", "speaker", "text"],
        ["0:00.0", "1:23.5", 0, "x"],
    ])
    segs = parse_xlsx(p)
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] == pytest.approx(83.5)


def test_parse_xlsx_speaker_string_form(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["start_time", "end_time", "speaker", "text"],
        [0.0, 1.0, "Speaker 1", "x"],
        [1.0, 2.0, "Sp2", "y"],
        [2.0, 3.0, "S3", "z"],
    ])
    segs = parse_xlsx(p)
    # parse_speaker: "Speaker 1" / "Sp2" / "S3" 一律抽數字 - 1 → 0-indexed
    assert segs[0]["speaker"] == 0
    assert segs[1]["speaker"] == 1
    assert segs[2]["speaker"] == 2


def test_parse_xlsx_skip_blank_rows(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["start_time", "end_time", "speaker", "text"],
        [0.0, 1.0, 0, "hello"],
        [None, None, None, None],
        [1.0, 2.0, 0, "world"],
    ])
    segs = parse_xlsx(p)
    assert len(segs) == 2


def test_parse_xlsx_missing_column_raises(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["start_time", "end_time", "speaker"],  # 缺 text
        [0.0, 1.0, 0],
    ])
    with pytest.raises(AppError) as ei:
        parse_xlsx(p)
    assert ei.value.code == ErrorCode.IMPORT_PARSE_FAILED
    assert "text" in str(ei.value.detail)


def test_parse_xlsx_invalid_time_raises(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["start_time", "end_time", "speaker", "text"],
        ["not-a-time", 1.0, 0, "x"],
    ])
    with pytest.raises(AppError) as ei:
        parse_xlsx(p)
    assert ei.value.code == ErrorCode.IMPORT_INVALID_TIME


def test_parse_xlsx_column_order_irrelevant(tmp_path: Path):
    p = _make_xlsx(tmp_path, [
        ["text", "speaker", "end_time", "start_time"],  # 顛倒順序
        ["hello", 0, 1.0, 0.0],
    ])
    segs = parse_xlsx(p)
    assert segs[0] == {"start": 0.0, "end": 1.0, "speaker": 0, "text": "hello"}
