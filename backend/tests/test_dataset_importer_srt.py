from pathlib import Path
from app.services.dataset_importer import parse_srt


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "label.srt"
    p.write_text(content, encoding="utf-8")
    return p


def test_parse_srt_with_speaker_prefix(tmp_path: Path):
    p = _write(tmp_path, """1
00:00:00,000 --> 00:00:03,450
Speaker 1: 早安

2
00:00:03,450 --> 00:00:07,200
Speaker 2: 你好
""")
    segs = parse_srt(p)
    assert len(segs) == 2
    assert segs[0] == {"start": 0.0, "end": 3.45, "speaker": 0, "text": "早安"}
    assert segs[1] == {"start": 3.45, "end": 7.20, "speaker": 1, "text": "你好"}


def test_parse_srt_without_prefix_defaults_speaker_zero(tmp_path: Path):
    p = _write(tmp_path, """1
00:00:00,000 --> 00:00:03,000
這是一句沒有 prefix 的字幕

2
00:00:03,000 --> 00:00:06,000
這是第二句
""")
    segs = parse_srt(p)
    assert all(s["speaker"] == 0 for s in segs)
    assert segs[0]["text"] == "這是一句沒有 prefix 的字幕"


def test_parse_srt_full_width_colon(tmp_path: Path):
    p = _write(tmp_path, """1
00:00:00,000 --> 00:00:03,000
Speaker 1：早安
""")
    segs = parse_srt(p)
    assert segs[0] == {"start": 0.0, "end": 3.0, "speaker": 0, "text": "早安"}


def test_parse_srt_multi_line_text(tmp_path: Path):
    p = _write(tmp_path, """1
00:00:00,000 --> 00:00:05,000
Speaker 2: 第一行
第二行
""")
    segs = parse_srt(p)
    assert segs[0]["speaker"] == 1
    # pysrt text 跨行用 "\n"，prefix 抽完後 text 含 "第一行\n第二行"
    assert "第一行" in segs[0]["text"] and "第二行" in segs[0]["text"]


def test_parse_srt_speaker_three_digits(tmp_path: Path):
    p = _write(tmp_path, """1
00:00:00,000 --> 00:00:01,000
Speaker 10: x
""")
    segs = parse_srt(p)
    # 1-based 10 → 0-indexed 9
    assert segs[0]["speaker"] == 9
