"""驗證 Job model 新欄位 + JobSource enum 新成員。"""
from app.models import Job, JobSource


def test_jobsource_youtube_fetch_exists():
    assert JobSource.YOUTUBE_FETCH.value == "youtube_fetch"


def test_job_has_source_url_column():
    assert "source_url" in {c.name for c in Job.__table__.columns}


def test_job_has_reference_subtitles_column():
    cols = {c.name for c in Job.__table__.columns}
    assert "reference_subtitles" in cols
    assert "reference_subtitle_lang" in cols
