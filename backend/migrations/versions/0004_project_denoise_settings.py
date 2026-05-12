"""project_denoise_settings

加 Project.denoise_enabled + Project.denoise_model 欄位，支援 ASR 推論前降噪設定。
既有 rows 預設 denoise_enabled=0(False)、denoise_model='gtcrn'。

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "denoise_enabled",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "denoise_model",
            sa.String(20),
            server_default=sa.text("'gtcrn'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "denoise_model")
    op.drop_column("projects", "denoise_enabled")
