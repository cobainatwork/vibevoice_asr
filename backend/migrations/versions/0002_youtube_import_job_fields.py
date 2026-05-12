"""youtube_import_job_fields

新增 Job 表三個欄位以支援 YouTube 匯入功能：
- source_url: YouTube 影片來源 URL
- reference_subtitles: 下載的人工字幕（JSON 陣列，每項含 start_time / end_time / text / speaker_id）
- reference_subtitle_lang: 字幕語言代碼（例：zh-TW）

JobSource enum 新增 'youtube_fetch' 成員：
SQLite 用 VARCHAR 儲存 enum，不限制值，無需 ALTER TABLE。
未來遷移至 Postgres 時需補：
# op.execute("ALTER TYPE jobsource ADD VALUE 'youtube_fetch'")

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("source_url", sa.String(500), nullable=True))
    op.add_column("jobs", sa.Column("reference_subtitles", sa.JSON(), nullable=True))
    op.add_column("jobs", sa.Column("reference_subtitle_lang", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "reference_subtitle_lang")
    op.drop_column("jobs", "reference_subtitles")
    op.drop_column("jobs", "source_url")
