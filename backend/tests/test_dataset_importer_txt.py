import pytest
from pathlib import Path
from app.errors import AppError, ErrorCode
from app.services.dataset_importer import parse_txt


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "label.txt"
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_txt_basic(tmp_path: Path):
    p = _write(tmp_path, """[00:00:00.00] Speaker 1: 早安
[00:00:03.45] Speaker 2: 你好
""")
    # 注意：txt 解析需要 audio_duration 推算最後一行 end
    segs = parse_txt(p, audio_duration=7.20)
    assert len(segs) == 2
    assert segs[0] == {"start": 0.0, "end": pytest.approx(3.45), "speaker": 0, "text": "早安"}
    # 最後一行 end 用 audio_duration
    assert segs[1] == {"start": pytest.approx(3.45), "end": pytest.approx(7.20), "speaker": 1, "text": "你好"}


def test_parse_txt_skip_unmatched_line(tmp_path: Path):
    p = _write(tmp_path, """[00:00:00.00] Speaker 1: 第一句
這一行沒有時間戳，會被略過
[00:00:03.00] Speaker 2: 第二句
""")
    segs = parse_txt(p, audio_duration=5.0)
    assert len(segs) == 2
    assert segs[1]["text"] == "第二句"


def test_parse_txt_full_width_colon(tmp_path: Path):
    p = _write(tmp_path, """[00:00:00.00] Speaker 1：早安
""")
    segs = parse_txt(p, audio_duration=3.0)
    assert segs[0]["speaker"] == 0
    assert segs[0]["text"] == "早安"


def test_parse_txt_all_unmatched_raises(tmp_path: Path):
    p = _write(tmp_path, """這個檔案
完全沒有合法格式
""")
    with pytest.raises(AppError) as ei:
        parse_txt(p, audio_duration=5.0)
    assert ei.value.code == ErrorCode.IMPORT_PARSE_FAILED


def test_parse_txt_empty_file_raises(tmp_path: Path):
    p = _write(tmp_path, "")
    with pytest.raises(AppError) as ei:
        parse_txt(p, audio_duration=5.0)
    assert ei.value.code == ErrorCode.IMPORT_PARSE_FAILED
