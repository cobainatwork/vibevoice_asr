"""project_playback_speed

Project 加 playback_speed 欄位（float，預設 1.0）。
ASR 推論前用 ffmpeg atempo 調速，推論完 segments 時間戳 scale 回原 timeline。

SQLite < 3.35 用 batch_alter_table 模式。

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column(
                "playback_speed",
                sa.Float(),
                nullable=False,
                server_default=sa.text("1.0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("playback_speed")
