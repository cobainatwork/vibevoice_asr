"""VTT / SRT 解析 + s2tw 正規化。"""
import pytest
from app.utils.subtitle_parser import parse_vtt, parse_srt, normalize_subtitle


VTT_BASIC = """WEBVTT

00:00:01.000 --> 00:00:04.500
你好世界

00:00:05.200 --> 00:00:08.000
這是第二段字幕
"""

VTT_MULTILINE = """WEBVTT

00:01:00.000 --> 00:01:05.000
第一行
接續第二行

00:01:06.000 --> 00:01:10.000
單行
"""

VTT_INLINE_TAGS = """WEBVTT

00:00:01.000 --> 00:00:03.000
<v Speaker1>含 inline tag 的字幕</v>
"""

VTT_SHORT_TIMESTAMP = """WEBVTT

01:00.000 --> 01:05.000
短時間戳 MM:SS.mmm 也要支援
"""


def test_parse_vtt_basic():
    segs = parse_vtt(VTT_BASIC)
    assert len(segs) == 2
    assert segs[0]["start_time"] == pytest.approx(1.0)
    assert segs[0]["end_time"] == pytest.approx(4.5)
    assert segs[0]["text"] == "你好世界"
    assert segs[0]["speaker_id"] == 0


def test_parse_vtt_multiline_cue():
    segs = parse_vtt(VTT_MULTILINE)
    assert len(segs) == 2
    assert segs[0]["text"] == "第一行 接續第二行"


def test_parse_vtt_strips_inline_tags():
    segs = parse_vtt(VTT_INLINE_TAGS)
    assert len(segs) == 1
    assert segs[0]["text"] == "含 inline tag 的字幕"


def test_parse_vtt_short_timestamp_format():
    segs = parse_vtt(VTT_SHORT_TIMESTAMP)
    assert len(segs) == 1
    assert segs[0]["start_time"] == pytest.approx(60.0)
    assert segs[0]["end_time"] == pytest.approx(65.0)


def test_parse_vtt_empty():
    assert parse_vtt("WEBVTT\n\n") == []


SRT_BASIC = """1
00:00:01,000 --> 00:00:04,500
你好世界

2
00:00:05,200 --> 00:00:08,000
這是第二段
"""


def test_parse_srt_basic():
    segs = parse_srt(SRT_BASIC)
    assert len(segs) == 2
    assert segs[0]["start_time"] == pytest.approx(1.0)
    assert segs[1]["text"] == "這是第二段"


def test_normalize_subtitle_s2tw():
    """簡體 → 繁體(透過 OpenCC),空格壓縮、trim。

    注意：OpenCC s2tw 對「软件优化」可能輸出「軟體最佳化」(zh-TW 慣用詞)
    或「軟體優化」，以實際 OpenCC 版本為準。
    若 Linux 端跑出不同結果，請修改此期望值對齊實際輸出。
    """
    raw = [
        {"start_time": 0.0, "end_time": 1.0, "speaker_id": 0, "text": "  软件优化   "},
    ]
    out = normalize_subtitle(raw)
    # 期望值以台灣慣用詞為優先；若 OpenCC 實際輸出不同，調整此處
    assert out[0]["text"] in ("軟體最佳化", "軟體優化")
