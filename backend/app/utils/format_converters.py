"""
Output format converters — internal segments → SRT/VTT/TXT/CSV/XLSX.

Used by:
- Dataset export (§9.4)
- Job result download

See SPEC.md §9.4.
M3.5 milestone.
"""
from __future__ import annotations


def segments_to_srt(segments: list[dict]) -> str:
    """Render segments as SubRip (.srt) text. Speakers as 'Speaker N:' prefix."""
    # TODO(M3.5)
    raise NotImplementedError


def segments_to_vtt(segments: list[dict]) -> str:
    # TODO(M3.5)
    raise NotImplementedError


def segments_to_txt(segments: list[dict]) -> str:
    """`[hh:mm:ss.ms] Speaker N: text` per line."""
    # TODO(M3.5)
    raise NotImplementedError


def segments_to_csv(segments: list[dict]) -> str:
    """CSV with columns: start_time,end_time,speaker,text."""
    # TODO(M3.5)
    raise NotImplementedError


def segments_to_xlsx(segments: list[dict]) -> bytes:
    """Excel binary."""
    # TODO(M3.5): use openpyxl
    raise NotImplementedError


def segments_to_training_json(segments: list[dict], audio_path: str,
                              audio_duration: float, customized_context: list[str]) -> dict:
    """
    Convert internal segments (1-indexed speaker, float seconds) to training JSON
    (0-indexed speaker, 'start'/'end' keys).
    """
    return {
        "audio_duration": audio_duration,
        "audio_path": audio_path,
        "segments": [
            {
                "speaker": max(0, s["speaker_id"] - 1),  # 1-indexed → 0-indexed
                "text": s["text"],
                "start": s["start_time"],
                "end": s["end_time"],
            }
            for s in segments
        ],
        "customized_context": customized_context,
    }


def training_json_to_segments(label: dict) -> list[dict]:
    """Reverse: training JSON segments (0-indexed) → internal (1-indexed)."""
    return [
        {
            "start_time": float(s["start"]),
            "end_time": float(s["end"]),
            "speaker_id": int(s["speaker"]) + 1,  # 0-indexed → 1-indexed
            "text": str(s["text"]),
        }
        for s in label.get("segments", [])
    ]
